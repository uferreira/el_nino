# Scientific Reference — El Niño Phase Diagram Analysis

All examples use real data from NOAA CPC and UHSLC.

---

## The ENSO Attractor

### Phase space reconstruction and Takens' theorem

A dynamical system evolving in a high-dimensional state space leaves a
low-dimensional "shadow" in any scalar observable it produces. Takens (1981)
proved that a *d*-dimensional attractor can be faithfully reconstructed —
topologically equivalent to the original — from a sequence of measurements of
a single observable, provided at least 2*d* + 1 successive measurements are used
(time-delay embedding). For ENSO, where the attractor dimension is estimated
at roughly 2–4, a two-dimensional embedding should capture most of the structure.

The most natural 2D embedding for a smooth signal T(t) is the *phase portrait*:

```
x = T(t)
y = dT/dt
```

This is equivalent to a time-delay embedding with an infinitesimally short delay
(in the limit where delay → 0). In practice, we use the Fourier-interpolated
derivative from `deri_fourier`, which gives a smooth, analytically exact dT/dt
on a fine grid (≈ 6-day spacing for NDOTS = 5).

### Why T and dT/dt form a natural 2D phase space

The phase portrait (T, dT/dt) has a direct physical interpretation:

- **x-axis (T):** the instantaneous state of the system — hot or cold ocean
- **y-axis (dT/dt):** the tendency — warming or cooling

Together they define the phase-space velocity vector. The direction and speed of
the trajectory at any point reveal the dynamics: slow motion (small dT/dt)
near fixed points, fast motion (large dT/dt) during rapid transitions. El Niño
events appear as large loops: the system accelerates into the warm quadrant,
reaches a peak (dT/dt = 0), and decelerates back toward neutral. La Niña events
trace the analogous loop on the cold side.

### What the attractor geometry reveals

In a perfectly periodic system (e.g. a simple harmonic oscillator), the
trajectory closes exactly on itself, forming an ellipse. ENSO is quasi-periodic:
the trajectory almost closes but shifts slightly each cycle, filling a band of
finite width in phase space. This band is the ENSO attractor. Its geometry
encodes dynamical information:

- **Width of the band**: the degree of irregularity — wider bands correspond to
  more chaotic, less predictable ENSO variability.
- **Eccentricity**: the ratio of maximum dT/dt to maximum T anomaly reflects the
  oscillation frequency. A more elongated loop along the x-axis means slower
  oscillation relative to the amplitude.
- **Asymmetry between upper-right and lower-left quadrants**: El Niño events
  (upper right) tend to be stronger and shorter than La Niña events (lower
  left), consistent with the well-documented positive skewness of ENSO.
- **Gaps and clusters**: years when the trajectory passes through a particular
  region of phase space cluster together (e.g. the 1982–83, 1997–98, and
  2015–16 super-events trace nearly the same large loop). Ordinary years follow
  tighter, smaller loops.

### Difference between regular cycles and chaotic attractors

A regular limit cycle would produce a perfectly closed, time-invariant loop.
ENSO's attractor is neither closed nor time-invariant: successive cycles have
different amplitudes and durations, the trajectory drifts slightly from one
revolution to the next, and the variance of the loop size itself varies on
decadal timescales (related to the Pacific Decadal Oscillation modulating the
mean state of the tropical Pacific). This combination of quasi-periodicity and
irreproducibility is the hallmark of a familiar attractor with a fractional
Hausdorff dimension.

### El Niño events as excursions from the attractor

During a major El Niño event, the system temporarily leaves the neighbourhood
of the climatological mean-state orbit and executes a large excursion into the
warm, rapidly-warming quadrant. The size of the excursion (measured as the
maximum distance from the origin in phase space) is a good proxy for event
intensity. The 1997–98 event produced a loop roughly three times larger in
phase-space area than a moderate El Niño year.

---

## The Fourier Filter

### Calendar-aligned endpoints

Before the Fourier calculation, the production pipeline selects the earliest
observation whose calendar month matches the last observed month. Thus a live
record ending in July is analysed from its first available July, rather than
from a fixed January start. This discards only the leading partial seasonal
cycle, does not fabricate an endpoint, and prevents the annual cycle itself from
creating a large January-to-July boundary difference. The original Fortran
input used the same-month pattern (for example February-to-February); the
Python update must preserve it as the terminal month advances.

### The sine Fourier expansion on [0, NM1]

The filter operates on a finite time series of NT monthly values (t = 0..NT−1,
NM1 = NT−1). After removing the mean (HMEDIA) and a linear trend (connecting
STA[0] to STA[NT−1] with a straight line), the boundary-corrected series STA
satisfies STA[0] = STA[NM1] = 0. This is the Dirichlet boundary condition for
the half-range sine expansion:

```
STA[t] ≈ Σ_{IW=1}^{NM1/2} FOURIER[IW] × sin(IW × t × π / NM1)
```

Coefficient IW corresponds to a period of 2 × NM1 / IW months (two "half-waves"
fit in the NM1-point window, hence the factor of 2). For a typical 600-month
record (NM1 = 599): IW = 7 corresponds to a period ≈ 171 months (14 years);
IW = 70 corresponds to ≈ 17 months; IW = 133 corresponds to ≈ 9 months.

The Fourier coefficients are computed as:

```
FOURIER[IW] = (2/NM1) × Σ_{IT=1}^{NM1} STA[IT] × sin(IW × IT × π / NM1)
```

Note: the summation index IT runs from 1 to NM1 (exclusive of endpoint 0),
using STA[1], STA[2], ..., STA[NM1−1], and STA[NM1] (which is 0 after
detrending). This corresponds to STA[IT+1] in the 1-indexed Fortran convention:

```fortran
FOURIER(IW) = FOURIER(IW) + (2./NM1) * STA(IT+1) * SIN(IW*IT*PI/NM1)
```

A known bug in the original notebook (cell 53) used `STA[:-1]` (elements
0..NT−2) instead of the correct `STA[1:]` (elements 1..NT−1). This shifts
the summation window by one sample, producing a systematically wrong set of
Fourier coefficients. The correct indexing, verified against the Fortran, is
`STA[1:NT]` in Python (0-based, elements 1..NT−1).

### The sigmoid window function FACTOR(IW)

Rather than a brick-wall cutoff (FACTOR = 1 below IW_cut, 0 above), the filter
uses a smooth sigmoid:

```
W₁ = NM1 / HN1       (mode number at the long-period edge)
W₂ = NM1 / HN2       (mode number at the short-period edge)
W₀ = (W₁ + W₂) / 2  (centre of the transition band)
DW₂ = |W₂ − W₁| / 2 (half-width of the transition)

FACTOR(IW) = 1 / (1 + exp((IW − W₀) / DW₂))
```

With HN1 = 10, HN2 = 9, and NM1 = 599 (600-month record):
- W₁ = 59.9  (modes below this are in the passband)
- W₂ = 66.6  (modes above this are in the stopband)
- W₀ = 63.2  (centre, FACTOR = 0.5)
- DW₂ = 3.35 (transition half-width in mode-number units)

The sigmoid suppresses Gibbs ringing by ensuring FACTOR is infinitely
differentiable — there is no discontinuity in the gain function or any of its
derivatives. A brick-wall truncation would cause the reconstructed series to
exhibit oscillatory artefacts near sharp gradients (e.g. at the edges of
strong El Niño events).

### Why Dirichlet boundary conditions (detrending before the FFT)

Without detrending, the finite series would have a discontinuous jump at the
endpoints (the last value is generally not equal to the first). A discontinuity
of magnitude Δ in a periodic extension of the series creates spectral leakage
of order Δ/IW in every mode IW — contaminating the low-frequency modes we
care about with power from all frequencies. The linear detrend forces both
endpoints to zero, eliminating this source of leakage and confining any
residual leakage to the truncation of the series itself (O(1/NM1) per mode).

### The reconstruction loop: why IIW runs from NM1/2 to NM1

In the Fortran:

```fortran
DO IIW = NM1/2, NM1
  IW = NT - IIW
  ...
END DO
```

When IIW = NM1/2, IW = NT − NM1/2 = NM1/2 + 1 (just outside the computed
range 1..NM1/2). When IIW = NM1, IW = NT − NM1 = 1. So IW runs from 1 to
NM1/2, but in reverse order (largest IW first). The reconstruction is
equivalent to summing all computed Fourier modes; the reversal has no effect
on the result. The `valid` mask in the Python code handles the boundary case
where IW falls outside [1, IW_max]:

```python
IIW_range = np.arange(NM1 // 2, NM1 + 1)
IW_recon  = NT - IIW_range         # IW = NT − IIW
valid     = (IW_recon >= 1) & (IW_recon <= IW_max)
IW_use    = IW_recon[valid]
```

### Interpolation and derivative formulas

`deri_fourier` computes on a fine grid of NTD = NM1 × NDOTS + 1 points,
indexed s = 0..NTDM1 (NTDM1 = NTD − 1). The fine grid is constructed so that
s = 0 coincides with the first monthly point, s = NDOTS coincides with the
second, and so on — i.e., monthly point j maps to fine-grid point s = j × NDOTS.

The argument in the sine/cosine reconstruction uses NTDM1:

```
sin(IW × s × π / NTDM1)
```

This maps s ∈ [0, NTDM1] to the same half-period argument range as the
original [0, NM1] mapping. The endpoints match: at s = 0 → argument = 0; at
s = NTDM1 → argument = IW × π.

The first derivative formula:

```
d/ds [FOURIER[IW] × sin(IW × s × π / NTDM1)] = FOURIER[IW] × (IW × π / NTDM1) × cos(...)
```

However, the Fortran (and the Python translation) uses NT rather than NTDM1
in the denominator:

```
VST[s] = Σ_IW FOURIER[IW] × (IW × π / NT) × cos(IW × s × π / NTDM1)
```

### Why VST uses NT not NM1 in the denominator

The derivative coefficient `IW × π / NT` rather than `IW × π / NM1` introduces
a small systematic scale factor of NM1/NT = (NT−1)/NT ≈ 0.9917 for NT = 120,
or 0.9983 for NT = 600. This is faithfully reproduced from the Fortran.
The physical interpretation is that the denominator sets the time unit:
using NT gives dT/dt in units of *observable per original time step (1 month)*,
consistent across records of different length. The 0.83% systematic discrepancy
from the exact analytical derivative is verified by `test_deri_fourier_derivative_accuracy`
and confirmed to remain below 1%.

---

## Sea Level as ENSO Proxy

### Steric and dynamic sea level response to ENSO

Sea level changes on ENSO timescales arise from two mechanisms:

1. **Steric (thermosteric) effect:** warmer water expands. A 1°C warming of the
   top 200 m of the ocean produces roughly 1–2 cm of sea level rise. During El
   Niño, the eastern Pacific thermocline deepens and surface temperatures rise,
   producing steric sea level increase of 10–20 cm at Callao.

2. **Dynamic (wind-driven) effect:** changes in the trade wind stress alter the
   slope of the sea surface across the Pacific. Weakened trades during El Niño
   allow the thermocline to relax from its tilted (west high, east low)
   climatological state toward a flatter configuration — raising sea level in
   the east and lowering it in the west.

Both effects reinforce each other at the eastern boundary (Callao) and oppose
each other at the western boundary (Palau) — explaining why the eastern and
western Pacific stations exhibit roughly opposite ENSO signals.

### Why Callao responds strongly to El Niño (coastal Kelvin waves)

The mechanism linking the central-Pacific wind anomaly to the eastern boundary
sea level response is the **coastal Kelvin wave**. When the trades weaken:

1. Equatorial Kelvin waves propagate eastward along the thermocline at ~2.5 m/s,
   reaching the South American coast in 1–2 months.
2. At the coast, the wave energy is partially reflected as Rossby waves
   (propagating back westward) and partially redirected into **coastal Kelvin
   waves** that propagate poleward along the coast of Peru and Chile.
3. The coastal Kelvin waves raise sea level and deepen the thermocline along the
   coast, suppressing the normal cold upwelling that drives Peruvian coastal
   fisheries. This is the "El Niño" of the original Peruvian fishermen.

The tide gauge at Callao (station 093) records this sea level rise directly and
nearly in phase with the central-Pacific SST anomaly. The response amplitude at
Callao (10–30 cm for moderate events) is substantially larger than the open-ocean
steric signal, making it an exceptionally sensitive ENSO indicator.

### Why Palau responds in opposite phase (western Pacific warm pool)

During El Niño, the western Pacific warm pool shifts eastward and trade winds
weaken. This causes:

- **Sea level fall** at the western boundary (Palau): the relaxation of trade
  winds allows the sea surface to tilt less steeply, drawing water from the
  west. The warm pool displacement eastward also reduces the steric sea level
  contribution.
- Sea level at Malakal/Palau (station 007) therefore **anti-correlates** with
  Callao: El Niño → Callao rises, Palau falls. La Niña → Callao falls, Palau
  rises.

In the phase diagram, the Palau attractor loops in the opposite sense to
Callao, with large excursions into the lower-left quadrant during El Niño
(sea level low and falling) rather than upper-right.

### Why Honolulu is a reference (mid-Pacific, moderate response)

Honolulu (station 057) lies at ~21°N in the central North Pacific, outside the
equatorial waveguide. Its ENSO response comes primarily from:

- Rossby wave reflections from the eastern boundary
- Large-scale thermocline depth changes propagating from the equatorial waveguide
  into the subtropical gyre

The response at Honolulu is moderate (5–15 cm for major events) and lags Callao
by 2–4 months. In phase space the Honolulu attractor is intermediate in size
between Callao (large eastern response) and the open-ocean background.

---

## Known Approximations and Limitations

### Monthly averaging of hourly sea level data

The pipeline aggregates hourly UHSLC observations to monthly means using
`resample("MS").mean()`. This discards sub-monthly variability: tidal signals
(M2 period ≈ 12.4 hours), storm surges, and intra-seasonal oscillations. For
ENSO analysis on interannual timescales this is appropriate and matches the
temporal resolution of the SST data. However, if the goal were to study
sub-monthly dynamics, the hourly data would need to be processed differently
(e.g. tide-removal by harmonic analysis before monthly averaging, as explored
in the original notebook cells 17–18).

### The UHSLC fill value −32767

UHSLC encodes missing observations as the minimum signed 16-bit integer
(−32767), not as NaN. This value corresponds to −32.767 metres — physically
impossible for any real tide gauge. The pipeline replaces it with NaN via
`_clean_obs` before aggregation. Failing to do so would drag monthly means
dramatically downward and corrupt the climatology computation.

### Timestamp snapping (±5 minutes)

UHSLC ERDDAP frequently delivers observations at times like 04:59:59 or
05:00:01 instead of exactly 05:00:00. The pipeline snaps timestamps within
5 minutes of a full clock hour to the exact hour. Without this correction,
two observations from the same clock hour would survive into the hourly-to-
monthly aggregation, producing artificially high variance and slightly biased
means for months with many such near-coincident pairs.

### The NT vs NM1 denominator in dT/dt (0.83% systematic error)

As described in the Filter section, the Fortran uses `IW × π / NT` rather than
the mathematically exact `IW × π / NM1` in the derivative formula. For NT = 120
(10-year record) this is a 0.83% systematic underestimate of dT/dt. For NT = 600
(50-year record) it drops to 0.17%. This is an intentional, faithful
reproduction of the Fortran behaviour — not a bug introduced by the Python
translation. It is verified and documented in `test_deri_fourier_derivative_accuracy`.

### The cell-53 off-by-one bug in the original notebook

The original Jupyter notebook (`ElNino_202605_movie_python_SST.ipynb`) contains
two Python implementations of the Fourier filter. The correct one is in cell 3
(used throughout this package). Cell 53 contains a loop-based version with a
subtle off-by-one bug:

```python
# WRONG (cell 53 of the original notebook):
FOURIER[IW] += (2.0 / NM1) * STA[:-1] * np.sin(IW * IT_arr * np.pi / NM1)
```

`STA[:-1]` selects elements 0..NT−2. The correct range is elements 1..NT−1
(matching Fortran's STA(IT+1) for IT = 1..NM1):

```python
# CORRECT:
FOURIER = (2.0 / NM1) * SIN_MAT.dot(STA[1:NT])
```

The shift by one sample causes all Fourier coefficients to be computed from the
wrong time window, producing a systematically incorrect filtered series. The
error is small for smooth signals (the phase shift of one sample ≈ 1 month is
tiny relative to the ENSO period of ~36 months) but non-negligible for sharp
features.

---

## References

**ENSO and SST indices:**
- Rasmusson, E.M. and Carpenter, T.H. (1982). Variations in Tropical Sea
  Surface Temperature and Surface Wind Fields Associated with the Southern
  Oscillation/El Niño. *Monthly Weather Review*, 110, 354–384.
  https://doi.org/10.1175/1520-0493(1982)110<0354:VITSST>2.0.CO;2

- Trenberth, K.E. (1997). The Definition of El Niño. *Bulletin of the American
  Meteorological Society*, 78(12), 2771–2777.
  https://doi.org/10.1175/1520-0477(1997)078<2771:TDOENO>2.0.CO;2

- Barnston, A.G., Chelliah, M. and Goldenberg, S.B. (1997). Documentation of a
  highly ENSO-related SST region in the equatorial Pacific. *Atmosphere–Ocean*,
  35(3), 367–383. https://doi.org/10.1080/07055900.1997.9649597

**Phase space reconstruction:**
- Takens, F. (1981). Detecting Familiar Attractors in Turbulence. In:
  *Dynamical Systems and Turbulence*, Springer Lecture Notes in Mathematics
  vol. 898, pp. 366–381. https://doi.org/10.1007/BFb0091924

- Packard, N.H., Crutchfield, J.P., Farmer, J.D. and Shaw, R.S. (1980).
  Geometry from a Time Series. *Physical Review Letters*, 45(9), 712–716.
  https://doi.org/10.1103/PhysRevLett.45.712

**Sea level and ENSO:**
- Wyrtki, K. (1985). Water displacements in the Pacific and the genesis of El
  Niño cycles. *Journal of Geophysical Research: Oceans*, 90(C4), 7129–7132.
  https://doi.org/10.1029/JC090iC04p07129

- Mitchum, G.T. (1994). Comparison of TOPEX sea surface heights and tide gauge
  sea levels. *Journal of Geophysical Research: Oceans*, 99(C12), 24541–24553.
  https://doi.org/10.1029/94JC01640

**Data archives:**
- NOAA CPC ENSO SST indices: https://www.cpc.ncep.noaa.gov/data/indices/
- UHSLC Research Quality and Fast Delivery sea level data:
  https://uhslc.soest.hawaii.edu/data/
- UHSLC ERDDAP service: https://uhslc.soest.hawaii.edu/erddap/

**Reference Fortran program:**
- The Fortran 77 source `filterfouriergr197501_202502.f` is the original
  implementation by the research group, which the Python package translates
  faithfully. Numerical equivalence is verified to within 0.005°C by
  `tests/test_filter_vs_fortran.py`.
