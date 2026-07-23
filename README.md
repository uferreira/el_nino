# El Niño Phase Diagram Analysis

This package reconstructs the low-dimensional attractor of the El Niño–Southern
Oscillation (ENSO) from two complementary ocean observables: sea surface
temperature (SST) in the NINO1+2 region and tide-gauge sea level at five
Pacific stations. A Fourier low-pass filter isolates variability on interannual
timescales (full periods longer than roughly 18–20 months), and the signal is
interpolated onto a fine grid so that the derivative dT/dt can be computed
analytically. The resulting phase-space trajectory (T vs dT/dt) traces the
ENSO attractor — the recurring loop that the coupled ocean–atmosphere system
follows as it oscillates between El Niño warm events and La Niña cold events.
The same trajectory can be animated as a rotating familiar attractor to reveal
the quasi-periodic, low-dimensional structure of ENSO dynamics.

---

## Scientific Background

**What is ENSO?**
The El Niño–Southern Oscillation is the dominant mode of interannual climate
variability on Earth. Every two to seven years, the equatorial Pacific alternates
between warm (El Niño) and cool (La Niña) phases, driven by feedbacks between
sea surface temperature, trade winds, and thermocline depth. ENSO affects
rainfall, drought, hurricane activity, and fisheries across the globe and is the
primary source of seasonal climate predictability.

**Why NINO1+2 SST?**
The NINO1+2 region (0–10°S, 90–80°W) sits in the far eastern equatorial Pacific,
directly off the coasts of Peru and Ecuador. It is the region where El Niño warming
first appears and where the signal is strongest — temperature anomalies of 3–5°C
during major events like 1982–83 and 1997–98. The NOAA CPC NINO1+2 index is a
monthly area-average SST derived from the Optimum Interpolation SST (OISST)
analysis, providing a continuous record from 1950 to the present.

**Why these five sea level stations?**
Sea level integrates both the thermal expansion of seawater (steric effect) and
wind-driven ocean circulation — making it a sensitive, physics-rich ENSO proxy.

- **Callao, Peru (UHSLC 093):** Eastern Pacific coastal station. During El Niño,
  downwelling Kelvin waves propagate eastward along the thermocline and suppress
  coastal upwelling, causing sea level to rise 10–30 cm. Callao is the canonical
  eastern boundary ENSO gauge.
- **Honolulu, Hawaii (UHSLC 057):** Mid-Pacific station with a moderate, broad
  ENSO response. Provides a reference for the central Pacific signal, roughly
  out of phase with Callao by ~90°.
- **Palau, western Pacific (UHSLC 007):** In the western Pacific warm pool, sea
  level responds in the opposite sense to the eastern Pacific — it falls during
  El Niño as surface warm water sloshes eastward and rises during La Niña.
- **Talara, Peru (UHSLC 092):** Eastern Pacific coastal record north of
  Callao. Sparse observations extend into August 2025, but July and August do
  not pass the 50% monthly coverage check. The usable monthly product ends in
  June 2025 and is marked stale.
- **La Libertad, Ecuador (UHSLC 091):** Eastern equatorial Pacific station with
  a long record that complements Callao and captures coastal ENSO sea-level
  variability close to the equator.

**The Fourier low-pass filter**
The filter (`passa_baixa`) suppresses full periods shorter than approximately
18 months. Its HN1=10 and HN2=9 parameters are half-periods because the method
uses a half-range sine expansion; the full-period transition is 18–20 months.
Intra-seasonal variability is discarded while the ENSO band passes through.
The sigmoid transition avoids Gibbs ringing. The series is then interpolated
to 5 sub-points per month (`deri_fourier`) so the phase-space trajectory is
reveal the attractor structure.

**The phase diagram T vs dT/dt**
Plotting the filtered temperature against its rate of change creates a
2-dimensional phase portrait. In a perfectly periodic system this would be a
closed ellipse. In the real climate system it forms a quasi-periodic strange
attractor: the trajectory revisits nearly the same region of phase space on ENSO
timescales but never closes exactly, revealing the chaotic dimension of ENSO
dynamics. El Niño events appear as large excursions into the upper-right quadrant
(T high and rising); La Niña events appear in the lower-left.

**Seasonal cycle removal**
The annual cycle is below the 18–20-month full-period transition and would be
attenuated by the low-pass filter. The climatological monthly mean is therefore
subtracted before filtering and re-added afterwards. The filter acts only on
interannual anomalies while the output retains the observed seasonal shape and
absolute physical units.

---

## Data Sources

| Dataset | Source | Station / Region | Period | Temporal resolution |
|---------|--------|-----------------|--------|---------------------|
| NINO1+2 SST | [NOAA CPC](https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices) | 0–10°S, 90–80°W | 1950–present | Monthly |
| Callao sea level | [UHSLC station 093](https://uhslc.soest.hawaii.edu) | Callao, Peru | 1970–present | Hourly → monthly |
| Talara sea level | [UHSLC station 092](https://uhslc.soest.hawaii.edu) | Talara, Peru | 1970–Jun 2025 usable | Hourly → monthly |
| La Libertad sea level | [UHSLC station 091](https://uhslc.soest.hawaii.edu) | La Libertad, Ecuador | 1949–present | Hourly → monthly |
| Honolulu sea level | [UHSLC station 057](https://uhslc.soest.hawaii.edu) | Honolulu, Hawaii | 1905–present | Hourly → monthly |
| Palau sea level | [UHSLC station 007](https://uhslc.soest.hawaii.edu) | Malakal, Palau | 1969–present | Hourly → monthly |

### Sea-level monthly quality control

Historical SSH months require at least 50% of their possible hourly values. The
current UTC month may be included as preliminary after seven valid days. The
pipeline keeps a complete monthly calendar: internal missing or rejected months
are reconstructed by interpolating anomalies about the station's monthly
climatology, while leading and trailing gaps are never extrapolated. Combined
input files mark reconstructed rows with `gap_filled=1`; long gaps are also
reported visibly on the website.

The NOAA SST record before 1982 is supplemented by a local historical file
(`data/input/sst1950_1981.txt`) in the same 10-column format. The two segments
are joined at January 1982 with no overlap.

---

## The Filter

Before either Fourier stage, the pipeline aligns the analysis window so its
first and last observations are from the same calendar month. As the live
record advances, only the leading partial seasonal cycle is discarded (for
example, January–July becomes July–July). This preserves every recent
observation and avoids injecting an artificial seasonal jump into the endpoint
correction.

**`passa_baixa` — Fourier low-pass filter**
Computes sine Fourier coefficients for modes IW = 1 to NM1/2 (where NM1 = NT−1),
then applies a sigmoid gain function:

```
FACTOR(IW) = 1 / (1 + exp((IW − W₀) / DW₂))
```

with W₁ = NM1/HN1, W₂ = NM1/HN2, W₀ = (W₁+W₂)/2, DW₂ = |W₂−W₁|/2.
Modes well below W₁ (long periods, ENSO band) receive gain ≈ 1.
Modes well above W₂ (short periods, weather noise) receive gain ≈ 0.
The transition is smooth, suppressing Gibbs ringing.

Parameters in `config.yaml`:

```yaml
filter:
  HN1: 10.0   # half-period parameter → 20-month full-period pass edge
  HN2: 9.0    # half-period parameter → 18-month full-period stop edge
  NDOTS: 5    # sub-points per monthly interval for interpolation
```

**Why Fourier instead of Butterworth?**
The Fourier reconstruction follows the reference Fortran 77 code and matches
its reconstructed values within the 0.01 output precision. The derivative uses
the corrected monthly scale described below. The method introduces zero phase
distortion: each spectral mode is independently scaled,
so the reconstructed trajectory preserves the timing of ENSO events exactly.

**`deri_fourier` — interpolation and derivative**
Reconstructs the filtered series on NTD = (NT−1)×NDOTS + 1 fine-grid points
and simultaneously computes dT/dt analytically from the Fourier coefficients.
For NDOTS = 5 and a 600-month record, NTD = 2996 points (spacing ≈ 6 days).

---

## Validation

The Python implementation follows the Fortran 77 reference program
`filterfouriergr197501_202502.f`. An always-running literal loop oracle checks
the vectorized filter; an optional gfortran test compares reconstructed values.
The derivative is checked against an exact analytical sine mode because Python
corrects the Fortran's `NT` denominator to the true `NT−1` monthly span. The
34-month passband mode survives with amplitude ratio 0.9998; the 6-month
stopband mode is suppressed to amplitude ratio < 10⁻⁶.

---

## Installation

**Requirements:** Python ≥ 3.9, gfortran (optional, for Fortran validation test)

```bash
# 1. Clone the repository
git clone <repo-url>
cd el_nino

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install the package in editable mode
pip install -e .

# 4. Place the historical SST file in the expected location
mkdir -p data/input
cp /path/to/sst1950_1981.txt data/input/
```

The historical SST file covers January 1950 – December 1981 in the same
10-column format as the NOAA CPC online file. All post-1981 data are
downloaded automatically from NOAA CPC at runtime.

---

## Live Website

The interactive phase diagram and Duffing equation simulator are live at:

**https://uferreira.github.io/el_nino/**

The website shows:
- Observed ENSO attractor (SST NINO1+2, 1975–2026)
- Observed sea level attractor (Callao, Peru, 1970–2026)
- Interactive Duffing equation simulator
- Synchronized comparison animation with timeline scrubber
- Poincaré section (3 datasets)
- 3D familiar attractor (12 monthly samples per year)

---

## Quick Start

**1. Run the SST pipeline and plot the phase diagram**

```python
from el_nino.pipeline import run_sst, load_output
from el_nino.plots import plot_phase_diagram, animate_phase_diagram

result = run_sst(
    local_file="data/input/sst1950_1981.txt",
    ano_inicio=1975,
    HN1=10.0, HN2=9.0, NDOTS=5,
    output_file="data/output/sst_filtered.dat",
)
print(f"SIGMA30 = {result['sigma30']:.4f} °C")

data = load_output("data/output/sst_filtered.dat")
fig = plot_phase_diagram(
    data, title="NINO1+2 SST Attractor",
    xlabel="Temperature (°C)", xlim=[17.5, 32.5], ylim=[-2.5, 2.5],
    save_path="data/output/sst_phase_diagram.png",
)
```

**2. Run the sea level pipeline for Callao**

```python
from el_nino.pipeline import run_sea_level, load_output
from el_nino.plots import animate_phase_diagram

result = run_sea_level(
    station_id="093", station_name="Callao",
    start_date="1905-01-01",
    HN1=10.0, HN2=9.0, NDOTS=5,
    output_file="data/output/callao_filtered.dat",
)
data = load_output("data/output/callao_filtered.dat")
ani = animate_phase_diagram(
    data, title="Callao Sea Level Attractor",
    xlabel="Sea level anomaly (mm)", xlim=[-300, 300], ylim=[-60, 60],
    remove_mean=True, save_path="data/output/callao_animation.mp4",
)
```

**3. Run all configured datasets at once from config.yaml**

```python
from el_nino.pipeline import run_all
from el_nino.plots import animate_all_from_config

results = run_all("config.yaml")          # downloads data, filters, writes .dat files
animate_all_from_config("config.yaml")   # reads .dat files, saves four .mp4 animations
```

---

## Module Reference

| Module | Function | What it does |
|--------|----------|--------------|
| `el_nino.filter` | `passa_baixa(HN1, HN2, ST0)` | Fourier low-pass filter; returns filtered series (NT,) |
| `el_nino.filter` | `deri_fourier(NDOTS, ST0)` | Fourier interpolation + derivative; returns SST, VST, AST on fine grid |
| `el_nino.filter` | `compute_sigma(ST0, ST_filtered, ST_interp, NDOTS)` | RMS filter residual (SIGMA30) and interpolation residual (SIGMA04) |
| `el_nino.download` | `load_sst(local_file, ano_inicio)` | Load NINO1+2 SST from local file + NOAA CPC download |
| `el_nino.download` | `load_sea_level(station_id, station_name, start_date)` | Download hourly UHSLC sea level, aggregate to monthly |
| `el_nino.download` | `load_from_config(config_path)` | Load all configured datasets from config.yaml |
| `el_nino.pipeline` | `run_sst(...)` | Full SST pipeline: download → filter → write .dat |
| `el_nino.pipeline` | `run_sea_level(...)` | Full sea level pipeline for one station |
| `el_nino.pipeline` | `run_all(config_path)` | Run every configured SST and sea-level pipeline |
| `el_nino.pipeline` | `load_output(output_file)` | Parse a .dat output file into NumPy arrays |
| `el_nino.plots` | `plot_phase_diagram(data, ...)` | Static T vs dT/dt figure with blue→red time gradient |
| `el_nino.plots` | `animate_phase_diagram(data, ...)` | Animated attractor: gray trail, red tail, blue dot |
| `el_nino.plots` | `plot_timeseries(data, ...)` | T and dT/dt vs time on twin y-axes |
| `el_nino.plots` | `animate_all_from_config(config_path)` | Create and save all four animations from config.yaml |

---

## Repository Structure

```
el_nino/
├── config.yaml                  # Filter parameters and station metadata
├── pyproject.toml               # Package metadata and dependencies
├── README.md                    # This file
│
├── data/
│   ├── input/
│   │   └── sst1950_1981.txt     # Historical NINO1+2 SST (1950–1981)
│   └── output/                  # Generated .dat, .png, .mp4 files
│
├── docs/
│   ├── USAGE.md                 # Practical usage guide with copy-paste recipes
│   └── SCIENCE.md               # Scientific reference (filter math, attractor theory)
│
├── scripts/
│   ├── run_all.py               # Run all four pipelines and save animations
│   └── run_sst_test.py          # End-to-end SST smoke test (downloads real data)
│
├── src/el_nino/
│   ├── filter.py                # passa_baixa, deri_fourier, compute_sigma
│   ├── download.py              # load_sst, load_sea_level, load_from_config
│   ├── pipeline.py              # run_sst, run_sea_level, run_all, load_output
│   └── plots.py                 # plot_phase_diagram, animate_phase_diagram, plot_timeseries
│
└── tests/
    └── test_filter_vs_fortran.py  # Numerical validation against reference Fortran
```
