"""
el_nino.filter
==============
Core mathematical functions: Fourier low-pass filter and Fourier
interpolation/differentiation.

Direct translation of SUBROUTINE PASSA_BAIXA and SUBROUTINE DERI_FOURIER
from the reference Fortran 77 implementation:
    filterfouriergr197501_202502.f

Corresponds to the vectorised Python in cell 3 of:
    ElNino_202605_movie_python_SST.ipynb
NOT the loop version in cell 53, which has a known off-by-one bug
(uses STA[:-1] instead of STA[1:]).
"""

import numpy as np


def passa_baixa(HN1: float, HN2: float, ST0: np.ndarray) -> np.ndarray:
    """
    Fourier low-pass filter — direct translation of SUBROUTINE PASSA_BAIXA.

    Removes high-frequency variability from a monthly time series while
    preserving El Niño–related oscillations at periods longer than
    roughly HN1–HN2 months. The transition from pass to stop is
    sigmoid-shaped, so there is no Gibbs ringing.

    Physical motivation
    -------------------
    ENSO operates on interannual timescales (2–7 years). Intra-seasonal
    variability (3–6 months) is noise for ENSO analysis. With HN1=10 and
    HN2=9 the filter's −3 dB point is near 9.5 months, cleanly separating
    seasonal from ENSO-scale signals.

    Why Fourier instead of Butterworth?
    ------------------------------------
    Exact correspondence with the reference Fortran code is required for
    reproducibility of the published phase-space diagrams and animation
    outputs. A Butterworth or other IIR filter produces a numerically
    different trajectory in (T, dT/dt) space. The Fourier approach also
    has a natural interpretation: each spectral mode is independently
    scaled, with no phase distortion.

    Filter design (sigmoid window)
    --------------------------------
    The transition band runs from mode W1 = NM1/HN1 (pass edge, longer
    periods) to W2 = NM1/HN2 (stop edge, shorter periods). Each Fourier
    coefficient is multiplied by:

        FACTOR(IW) = 1 / (1 + exp( (IW − W0) / DW2 ))

    where W0 = (W1+W2)/2 is the centre and DW2 = |W2−W1|/2 is the
    half-width. Modes well below W1 receive FACTOR ≈ 1 (pass). Modes
    well above W2 receive FACTOR ≈ 0 (stop). Modes in between are
    smoothly interpolated, avoiding the ringing that a brick-wall
    truncation would produce.

    Parameters
    ----------
    HN1 : float
        Low-frequency (long-period) edge of the transition band in months.
        Typically 10.0. Modes with period > HN1 are passed with FACTOR ≈ 1.
    HN2 : float
        High-frequency (short-period) edge of the transition band in months.
        Typically 9.0. Must satisfy HN2 < HN1 for a low-pass filter.
        Modes with period < HN2 are suppressed with FACTOR ≈ 0.
    ST0 : ndarray of shape (NT,)
        Input monthly time series. Should be anomalies (annual cycle
        removed before calling) to prevent leakage from the 12-month
        harmonic into the El Niño band.

    Returns
    -------
    STB : ndarray of shape (NT,)
        Filtered time series. The mean and linear trend of ST0 are
        preserved (removed before filtering, restored afterwards).

    Notes
    -----
    Corresponds to SUBROUTINE PASSA_BAIXA(HN1, HN2, STB, ST0, NT) in
    filterfouriergr197501_202502.f.
    """
    NT  = len(ST0)
    NM1 = NT - 1
    PI  = np.pi

    # Remove mean and linear trend before computing Fourier coefficients.
    # The Fortran forces STA[0] = STA[NT-1] = 0 after detrending (Dirichlet
    # boundary conditions), which prevents spectral leakage at the endpoints
    # of the finite series.
    STA    = ST0.copy()
    HMEDIA = float(STA.mean())
    STA   -= HMEDIA
    FIRST  = float(STA[0])
    HLAST  = float(STA[NT - 1])
    STA   -= FIRST + np.arange(NT) * (HLAST - FIRST) / NM1

    # Compute sine Fourier coefficients for modes IW = 1..NM1//2.
    # Fortran (1-based): FOURIER(IW) = (2/NM1)*Σ_{IT=1}^{NM1} STA(IT+1)*sin(IW*IT*π/NM1)
    # Python  (0-based): STA[1..NT-1] — NOT STA[:-1], which shifts the window
    #                    one sample to the left and produces the cell-53 bug.
    IW_max  = NM1 // 2
    IW_arr  = np.arange(1, IW_max + 1, dtype=np.float64)   # modes 1..IW_max
    IT_arr  = np.arange(1, NM1 + 1,   dtype=np.float64)    # summation index 1..NM1
    SIN_MAT = np.sin(np.outer(IW_arr, IT_arr) * PI / NM1)  # shape (IW_max, NM1)
    FOURIER = (2.0 / NM1) * SIN_MAT.dot(STA[1:NT])         # shape (IW_max,)

    # Sigmoid filter window: W1 and W2 are the mode numbers corresponding
    # to the two cutoff periods. DW2 controls the steepness of the transition.
    W1  = NM1 / HN1
    W2  = NM1 / HN2
    DW2 = abs(W2 - W1) / 2.0
    W0  = (W1 + W2) / 2.0

    # Reconstruct following the exact Fortran loop IIW = NM1//2..NM1, IW = NT−IIW.
    # Only IW values in [1, IW_max] have non-zero FOURIER entries; the `valid`
    # mask discards the one boundary point that falls outside this range.
    IIW_range = np.arange(NM1 // 2, NM1 + 1, dtype=np.int64)
    IW_recon  = NT - IIW_range                                  # IW = NT − IIW
    valid     = (IW_recon >= 1) & (IW_recon <= IW_max)
    IW_use    = IW_recon[valid]

    FACTOR  = 1.0 / (1.0 + np.exp((IW_use - W0) / DW2))
    F_coefs = FOURIER[IW_use - 1]                               # 0-based index into FOURIER

    # (IT−1) runs 0..NT-1, matching Fortran's sin(IW*(IT-1)*π/NM1) for IT=1..NT.
    IT_out  = np.arange(NT, dtype=np.float64)
    SIN_OUT = np.sin(np.outer(IW_use.astype(np.float64), IT_out) * PI / NM1)
    STB     = (FACTOR * F_coefs) @ SIN_OUT                      # shape (NT,)

    # Restore the mean and linear trend that were removed before filtering.
    STB += HMEDIA + FIRST + IT_out * (HLAST - FIRST) / NM1

    return STB


def deri_fourier(
    NDOTS: int, ST0: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fourier interpolation and differentiation — direct translation of
    SUBROUTINE DERI_FOURIER.

    Interpolates a filtered monthly series onto a finer grid of NDOTS
    sub-points per monthly interval, simultaneously computing the first
    and second time derivatives analytically from the Fourier
    representation.

    Why 5 sub-points per month?
    ----------------------------
    At NDOTS=5 the output spacing is approximately 6 days. This is fine
    enough to trace the ENSO attractor in phase space without aliasing,
    while keeping file sizes manageable. The smoother curve in (T, dT/dt)
    space reveals the attractor structure: the characteristic El Niño
    loop (warming flank → peak → cooling flank) becomes a smooth closed
    orbit rather than a coarse polygon connecting monthly samples.

    What VST represents physically
    --------------------------------
    VST is the rate of change of the observable: °C/month for SST, or
    mm/month for sea level. It is the y-axis of the phase diagram.
    Together with the observable itself on the x-axis, it defines the
    phase-space trajectory. Fixed points, limit cycles, and strange
    attractors in (T, dT/dt) space characterise the low-dimensional
    dynamics of the coupled ocean–atmosphere system.

    The denominator in the derivative formula uses NT (the number of
    original monthly points), not NTDM1 (the number of interpolated
    points minus one). This is faithful to the Fortran and gives VST in
    natural units of [observable unit] per original monthly step, making
    it directly comparable across different series lengths.

    Parameters
    ----------
    NDOTS : int
        Sub-divisions per monthly interval. Typically 5.
    ST0 : ndarray of shape (NT,)
        Filtered monthly time series with the annual cycle already
        re-added. This must be SST3 (= passa_baixa output + seasonal
        climatology), NOT the anomaly SST2. Including the annual cycle
        ensures the interpolated trajectory follows the full seasonal loop.

    Returns
    -------
    SST : ndarray of shape (NTD,)
        Interpolated time series. NTD = (NT−1)*NDOTS + 1.
    VST : ndarray of shape (NTD,)
        First derivative dT/dt in units of [T unit] per month.
    AST : ndarray of shape (NTD,)
        Second derivative d²T/dt² in units of [T unit] per month².

    Notes
    -----
    Corresponds to SUBROUTINE DERI_FOURIER(AST, VST, SST, NDOTS, ST0, NT)
    in filterfouriergr197501_202502.f.
    """
    NT    = len(ST0)
    NM1   = NT - 1
    PI    = np.pi
    NTD   = NM1 * NDOTS + 1    # total interpolated output points
    NTDM1 = NTD - 1

    # Remove mean and linear trend — identical preprocessing to passa_baixa.
    STA    = ST0.copy()
    HMEDIA = float(STA.mean())
    STA   -= HMEDIA
    FIRST  = float(STA[0])
    HLAST  = float(STA[NT - 1])
    STA   -= FIRST + np.arange(NT) * (HLAST - FIRST) / NM1

    # Fourier coefficients — same formula as in passa_baixa.
    # Both subroutines start from the same spectral decomposition;
    # the difference is only in the output grid and the absence of the
    # sigmoid window here (all modes are kept for interpolation).
    IW_max  = NM1 // 2
    IW_arr  = np.arange(1, IW_max + 1, dtype=np.float64)
    IT_arr  = np.arange(1, NM1 + 1,   dtype=np.float64)
    SIN_MAT = np.sin(np.outer(IW_arr, IT_arr) * PI / NM1)
    FOURIER = (2.0 / NM1) * SIN_MAT.dot(STA[1:NT])

    # Reconstruction indices — same Fortran loop as passa_baixa.
    # No sigmoid window here: all valid modes contribute with FACTOR = 1.
    IIW_range = np.arange(NM1 // 2, NM1 + 1, dtype=np.int64)
    IW_recon  = NT - IIW_range
    valid     = (IW_recon >= 1) & (IW_recon <= IW_max)
    IW_use    = IW_recon[valid]
    F_coefs   = FOURIER[IW_use - 1]
    IW_f      = IW_use.astype(np.float64)

    # Output grid: (IT−1) runs 0..NTD-1 over the fine time axis.
    # Arguments use NTDM1 so the fine grid maps [0, NTDM1] → [0, NM1]
    # (first and last fine points coincide with the first and last monthly points).
    IT_out  = np.arange(NTD, dtype=np.float64)
    ARG     = np.outer(IW_f, IT_out) * PI / NTDM1
    SIN_ARG = np.sin(ARG)
    COS_ARG = np.cos(ARG)

    # Interpolated series: Fourier modes summed on the fine grid, no weighting.
    SST = F_coefs @ SIN_ARG

    # First derivative: d/dt[F*sin(IW*t*π/NTDM1)] = F*(IW*π/NT)*cos(...)
    # Faithful to Fortran: denominator is NT (not NTDM1). This gives VST in
    # units of °C or mm per original monthly time step.
    VST = (F_coefs * (IW_f * PI / NT)) @ COS_ARG

    # Second derivative: −F*(IW*π/NT)² * sin(...)
    AST = -(F_coefs * (IW_f * PI / NT) ** 2) @ SIN_ARG

    # Restore mean and linear trend.
    # SST: re-add full trend using NTDM1 so endpoints match the input series.
    # VST: only the trend slope contributes (the trend value cancels in the
    #      derivative), matching Fortran's VST(IT) += (HLAST-FIRST)/NM1.
    SST += HMEDIA + FIRST + IT_out * (HLAST - FIRST) / NTDM1
    VST += (HLAST - FIRST) / NM1

    return SST, VST, AST


def compute_sigma(
    ST0: np.ndarray,
    ST_filtered: np.ndarray,
    ST_interp: np.ndarray,
    NDOTS: int,
) -> tuple[float, float]:
    """
    Compute the two RMS diagnostic errors reported by the Fortran program.

    SIGMA30 measures how much high-frequency energy passa_baixa removed.
    A large SIGMA30 indicates strong intra-seasonal variability was present
    in the input. A value near zero means the raw series was already smooth
    (no energy above the cutoff).

    SIGMA04 measures how faithfully deri_fourier reproduces the original
    monthly values at the original time steps (IREST==0 points in the
    Fortran output). Since deri_fourier uses the same Fourier modes as
    passa_baixa, SIGMA04 should be close to SIGMA30: both reflect the
    energy of the modes that were removed by the low-pass filter. Any
    difference reveals numerical precision effects or a mismatch between
    the filter and interpolation bases.

    Parameters
    ----------
    ST0 : ndarray of shape (NT,)
        Original (unfiltered) monthly time series.
    ST_filtered : ndarray of shape (NT,)
        Output of passa_baixa with the seasonal climatology re-added
        (SST3 in notebook notation).
    ST_interp : ndarray of shape (NTD,)
        SST output of deri_fourier (the interpolated series on the
        fine grid). Must have been computed from ST_filtered, not ST0.
    NDOTS : int
        Sub-divisions per month used in deri_fourier. Needed to extract
        the original monthly time steps from ST_interp via [::NDOTS].

    Returns
    -------
    sigma30 : float
        RMS( ST_filtered − ST0 ) — low-pass filter residual.
    sigma04 : float
        RMS( ST0 − ST_interp[::NDOTS] ) — interpolation residual at
        the original monthly time steps.

    Notes
    -----
    Named SIGMA30 and SIGMA04 following the Fortran variable names
    (WRITE(6,1795) and WRITE(6,1296) in filterfouriergr197501_202502.f).
    """
    # SIGMA30: RMS of the difference between filtered and raw series.
    # Measures total high-frequency power removed by passa_baixa.
    sigma30 = float(np.sqrt(np.mean((ST_filtered - ST0) ** 2)))

    # SIGMA04: RMS error at the original monthly points.
    # ST_interp[::NDOTS] selects indices 0, NDOTS, 2*NDOTS, ..., (NT-1)*NDOTS,
    # which are the IREST==0 points in Fortran notation — one per input month.
    sigma04 = float(np.sqrt(np.mean((ST0 - ST_interp[::NDOTS]) ** 2)))

    return sigma30, sigma04


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Verify correctness of all three functions using synthetic signals.

    Uses exact Fourier modes so the amplitude ratios are analytically
    predictable (no spectral leakage, no edge-effect ambiguity):

      Mode IW=7  with NT=120: period = NM1/7 = 119/7 ≈ 17 months
                               → well inside passband (>10 months)
      Mode IW=40 with NT=120: period = NM1/40 = 119/40 ≈ 3 months
                               → well inside stopband (<9 months)

    Tests:
      1. 17-month component survives  (amplitude ratio > 0.9)
      2.  3-month component suppressed (amplitude ratio < 0.1)
      3. deri_fourier output length == (NT-1)*NDOTS + 1
      4. VST[0] > 0 when input is rising at t=0
      5. compute_sigma returns finite values
    """
    print("Running self-test …")

    NT    = 120
    NM1   = NT - 1
    NDOTS = 5
    NTD   = NM1 * NDOTS + 1
    t     = np.arange(NT, dtype=float)

    # Exact half-period sine modes: sin(IW0 * t * π/NM1).
    # For integer IW0, both endpoints are exactly zero → no detrending effect.
    IW_SLOW = 7     # period ≈ 17 months — passband
    IW_FAST = 40    # period ≈  3 months — stopband
    A = 2.0

    y_slow = A * np.sin(IW_SLOW * t * np.pi / NM1)
    y_fast = A * np.sin(IW_FAST * t * np.pi / NM1)

    # --- 1. Slow component (≈17 months) must survive the filter ---
    stb_slow = passa_baixa(10.0, 9.0, y_slow)
    ratio_slow = np.sqrt(np.mean(stb_slow ** 2)) / np.sqrt(np.mean(y_slow ** 2))
    assert ratio_slow > 0.9, (
        f"FAIL test 1: 17-month component suppressed — ratio = {ratio_slow:.4f}"
    )
    print(f"  PASS 1: 17-month component preserved  (amplitude ratio = {ratio_slow:.4f})")

    # --- 2. Fast component (≈3 months) must be blocked ---
    stb_fast = passa_baixa(10.0, 9.0, y_fast)
    ratio_fast = np.sqrt(np.mean(stb_fast ** 2)) / np.sqrt(np.mean(y_fast ** 2))
    assert ratio_fast < 0.1, (
        f"FAIL test 2: 3-month component leaked — ratio = {ratio_fast:.6f}"
    )
    print(f"  PASS 2: 3-month component suppressed  (amplitude ratio = {ratio_fast:.6f})")

    # --- 3. deri_fourier output length ---
    # Input to deri_fourier is the filtered series (annual cycle re-added;
    # no annual cycle in this synthetic test, so stb_slow serves as SST3).
    sst, vst, ast = deri_fourier(NDOTS, stb_slow)
    assert len(sst) == NTD, f"FAIL test 3: SST length {len(sst)} != {NTD}"
    assert len(vst) == NTD, f"FAIL test 3: VST length {len(vst)} != {NTD}"
    assert len(ast) == NTD, f"FAIL test 3: AST length {len(ast)} != {NTD}"
    print(f"  PASS 3: deri_fourier output length = {NTD}  (= (NT-1)*NDOTS + 1)")

    # --- 4. VST sign: positive at t=0 for a rising sine ---
    # y_slow = A*sin(IW_SLOW * t * π/NM1) is zero and increasing at t=0.
    # After filtering the slow mode passes through unchanged, so VST[0] > 0.
    assert vst[0] > 0, f"FAIL test 4: VST[0] = {vst[0]:.6f} (expected > 0)"
    print(f"  PASS 4: VST[0] > 0  (VST[0] = {vst[0]:.6f})")

    # --- 5. compute_sigma returns finite values ---
    sig30, sig04 = compute_sigma(y_slow, stb_slow, sst, NDOTS)
    assert np.isfinite(sig30), f"FAIL test 5: sigma30 not finite: {sig30}"
    assert np.isfinite(sig04), f"FAIL test 5: sigma04 not finite: {sig04}"
    print(
        f"  PASS 5: compute_sigma  sigma30 = {sig30:.6f},  sigma04 = {sig04:.6f}"
    )

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
