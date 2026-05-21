# El Niño Phase Diagram — Usage Guide

All examples use real data from NOAA CPC and UHSLC.

---

## 1. Installation and Setup

**Requirements:** Python ≥ 3.9. gfortran is optional and only needed if you
want to run the Fortran validation test.

```bash
git clone <repo-url>
cd el_nino

python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -e .
```

Obtain the historical SST file (1950–1981) and place it at the path the
pipeline expects:

```bash
mkdir -p data/input
cp /path/to/sst1950_1981.txt data/input/
```

Everything after January 1982 is downloaded automatically from NOAA CPC
each time you run the pipeline. No API keys or accounts are required.

---

## 2. Quick Start — Five Lines to Your First Phase Diagram

```python
from el_nino.pipeline import run_sst, load_output
from el_nino.plots import plot_phase_diagram

result = run_sst("data/input/sst1950_1981.txt", 1975, 10.0, 9.0, 5,
                 "data/output/sst.dat")
data = load_output("data/output/sst.dat")
plot_phase_diagram(data, "NINO1+2 SST Attractor", "Temperature (°C)",
                   [17.5, 32.5], [-2.5, 2.5],
                   save_path="data/output/sst_phase.png")
```

This downloads ~600 months of real NINO1+2 SST data from NOAA, runs the
Fourier filter, and saves a PNG showing the full attractor trajectory from
1975 to the present.

---

## 3. Reading and Understanding the Data

### What is NINO1+2 SST?

The NINO1+2 index is the area-averaged sea surface temperature over the
far eastern equatorial Pacific (0–10°S, 90–80°W). This region is the first
to warm during El Niño events: anomalies of 3–5°C above the climatological
mean were recorded in 1982–83 and 1997–98. The NOAA CPC provides a monthly
mean updated within days of the end of each month.

`load_sst` returns three parallel arrays:

```python
from el_nino.download import load_sst

data = load_sst(local_file="data/input/sst1950_1981.txt", ano_inicio=1975)
# data["IYR"]  — int32 array of calendar years  (e.g. [1975, 1975, ..., 2025])
# data["MES"]  — int32 array of months 1..12    (e.g. [1, 2, ..., 12, 1, ...])
# data["SST0"] — float64 array of NINO1+2 SST in °C
```

Typical values: 20–28°C in non-El Niño years, rising to 30–32°C during
strong El Niño events.

### What is UHSLC sea level data?

UHSLC (University of Hawaii Sea Level Center) maintains the world's primary
archive of quality-controlled long-record tide gauge data. The hourly Fast
Delivery (FD) product is updated within days of collection. Data are in
millimetres relative to station datum (station zero), a local reference
level that is internally consistent within each record.

```python
from el_nino.download import load_sea_level

data = load_sea_level(
    station_id="093",        # UHSLC numeric ID, zero-padded
    station_name="Callao",   # used in progress messages only
    start_date="1905-01-01", # ERDDAP returns whatever exists from this date
)
# data["IYR"]  — int32 array of years
# data["MES"]  — int32 array of months 1..12
# data["SL0"]  — float64 array of monthly mean sea level in mm
```

The pipeline performs several cleaning steps before returning monthly means:
timestamps are snapped to the nearest clock hour (UHSLC often delivers
04:59:59 instead of 05:00:00), the fill sentinel −32767 is replaced with
NaN, duplicates are dropped, and hourly observations are averaged to monthly
means via `resample("MS").mean()`.

### The output format from `load_output`

After running either pipeline, `load_output` parses the .dat file:

```python
from el_nino.pipeline import load_output

data = load_output("data/output/sst.dat")
# data["T"]     — float64 (NTD,): filtered + interpolated temperature
# data["dT"]    — float64 (NTD,): rate of change dT/dt
# data["year"]  — int32 (NTD,): calendar year for each fine-grid point
# data["month"] — int32 (NTD,): calendar month (1..12)
# data["irest"] — int32 (NTD,): sub-month index (0 = original monthly point)
```

`irest == 0` marks the original monthly grid points. `irest == 1..4` are the
four interpolated sub-points between consecutive monthly observations. For a
600-month record with NDOTS=5, NTD = 599 × 5 + 1 = 2996 fine-grid points.

---

## 4. The Fourier Filter

### What `passa_baixa` does step by step

1. **Remove the mean** from the input series ST0 → STA.
2. **Remove a linear trend** (connect the first and last values with a
   straight line and subtract it). This enforces Dirichlet boundary conditions
   (STA = 0 at both endpoints), suppressing spectral leakage from the endpoints
   into the interior.
3. **Compute sine Fourier coefficients** for modes IW = 1 to NM1//2
   (NM1 = NT − 1):
   ```
   FOURIER[IW] = (2/NM1) × Σ_{IT=1}^{NM1} STA[IT] × sin(IW × IT × π / NM1)
   ```
4. **Apply the sigmoid window**:
   ```
   FACTOR[IW] = 1 / (1 + exp((IW − W₀) / DW₂))
   ```
   Modes well below W₁ = NM1/HN1 receive FACTOR ≈ 1 (pass through).
   Modes well above W₂ = NM1/HN2 receive FACTOR ≈ 0 (suppressed).
5. **Reconstruct** the filtered series in the time domain.
6. **Restore mean and trend**.

### What HN1 and HN2 mean physically

- **HN1 = 10.0 months**: the low-frequency (long-period) edge of the transition
  band. Signals with period > 10 months pass with gain ≈ 1. This retains ENSO
  variability (2–7 year periods) and the annual cycle (12 months).
- **HN2 = 9.0 months**: the high-frequency (short-period) edge. Signals with
  period < 9 months are suppressed. Weather noise, the semi-annual harmonic,
  and intra-seasonal variability are removed.
- The **transition band** is narrow (9–10 months) and smooth. Any signal near
  9.5 months receives approximately half gain.

### What `deri_fourier` produces

`deri_fourier` uses the same Fourier coefficients as `passa_baixa` (no sigmoid
attenuation) and reconstructs the filtered series on a fine grid with NDOTS
sub-points per monthly interval:

```
NTD = (NT − 1) × NDOTS + 1
```

For NT = 600 months and NDOTS = 5: NTD = 2996 fine-grid points, approximately
one point every 6 days. At the same time it computes the first derivative analytically:

```
VST[s] = Σ_IW FOURIER[IW] × (IW × π / NT) × cos(IW × s × π / NTDM1)
```

This is the y-axis of the phase diagram. The physical units are °C/month for SST
or mm/month for sea level.

### How to interpret SIGMA30 and SIGMA04

Both diagnostics are printed when you run the pipeline:

```
SIGMA30 = 0.3842    # RMS(filtered − raw) in °C
SIGMA04 = 0.3619    # RMS(raw − interp_at_monthly_pts) in °C
```

- **SIGMA30** = RMS(SST3 − SST0): the total high-frequency energy that the
  filter removed. Larger values indicate stronger sub-10-month variability
  (e.g. a strong Madden–Julian Oscillation year). Typical values for the
  NINO1+2 record: 0.3–0.8°C.
- **SIGMA04** = RMS(SST0 − SST4[::NDOTS]): the reconstruction error at the
  original monthly grid points. This is the residual between the raw data and
  the Fourier-interpolated series at the same months. Should be close to but
  slightly smaller than SIGMA30, since the interpolation uses all modes
  (no sigmoid attenuation).

If SIGMA04 > SIGMA30, the interpolation is adding energy not present in the
filtered series — this would indicate a bug.

---

## 5. Running the Full Pipeline

### `run_sst` — complete example

```python
from el_nino.pipeline import run_sst

result = run_sst(
    local_file="data/input/sst1950_1981.txt",
    ano_inicio=1975,      # first year to use from the local file
    HN1=10.0,             # low-pass filter long-period edge (months)
    HN2=9.0,              # low-pass filter short-period edge (months)
    NDOTS=5,              # interpolation sub-points per month
    output_file="data/output/sst_filtered.dat",
)

# result keys:
print(f"NT      = {len(result['SST0'])}")    # number of monthly input points
print(f"NTD     = {len(result['SST4'])}")    # number of fine-grid output points
print(f"SIGMA30 = {result['sigma30']:.4f} °C")
print(f"SIGMA04 = {result['sigma04']:.4f} °C")
print(f"Output  : {result['output_file']}")
```

The output file is named automatically using the data date range:
`sva.2_filter_10_9_1975.2_2025.4_SAIDApy.dat` (example).

### `run_sea_level` — complete example

```python
from el_nino.pipeline import run_sea_level

result = run_sea_level(
    station_id="093",
    station_name="Callao",
    start_date="1905-01-01",
    HN1=10.0, HN2=9.0, NDOTS=5,
    output_file="data/output/sva.2_filter_Callao_SAIDApy.dat",
)

print(f"NT      = {len(result['SL0'])}")
print(f"SIGMA30 = {result['sigma30']:.1f} mm")
```

### `run_all` — all four datasets at once

```python
from el_nino.pipeline import run_all

results = run_all("config.yaml")
# results["sst"]      — dict from run_sst
# results["callao"]   — dict from run_sea_level for Callao
# results["honolulu"] — dict from run_sea_level for Honolulu
# results["palau"]    — dict from run_sea_level for Palau
```

`run_all` reads all parameters (filter cutoffs, station IDs, start dates,
local file path) from `config.yaml` so you do not need to pass them explicitly.

### `load_output` — reloading saved results

Once the .dat files exist, you can reload them without re-running the pipeline:

```python
from el_nino.pipeline import load_output

data = load_output("data/output/sva.2_filter_Callao_SAIDApy.dat")
# Returns dict with keys: T, dT, year, month, irest
```

---

## 6. Making Phase Diagrams

### `plot_phase_diagram` — static figure

```python
from el_nino.plots import plot_phase_diagram

fig = plot_phase_diagram(
    data=data,
    title="NINO1+2 SST Phase Space 1975–present",
    xlabel="Temperature (°C)",
    xlim=[17.5, 32.5],
    ylim=[-2.5, 2.5],
    remove_mean=False,          # True for sea level (plots anomaly)
    save_path="data/output/sst_phase.png",
)
```

The trajectory is drawn as a `LineCollection` with a blue (early) → red (late)
color gradient, so you can read the direction of time without a separate legend.
Reference lines at T = 0 and dT/dt = 0 mark the equilibrium boundaries.

For sea level use `remove_mean=True` — this subtracts the record mean from T
before plotting so the x-axis shows anomaly centred at zero, matching the
ylim values in config.yaml.

### `animate_phase_diagram` — saving as .mp4

Requires ffmpeg installed on your system (`brew install ffmpeg` on macOS or
`apt install ffmpeg` on Ubuntu).

```python
from el_nino.plots import animate_phase_diagram

ani = animate_phase_diagram(
    data=data,
    title="Callao Sea Level Attractor",
    xlabel="Sea level anomaly (mm)",
    xlim=[-300, 300],
    ylim=[-60, 60],
    tail_months=12,             # length of the red trailing line
    fps=15,
    dpi=150,
    remove_mean=True,
    save_path="data/output/callao_animation.mp4",
)
```

Each frame shows:
- **Gray line**: the full trajectory from the beginning up to the current frame
- **Red line**: the last 12 months × 5 = 60 frames (one year of history)
- **Blue dot**: current position in phase space
- **Time label**: "YYYY MM" in the top-left corner

Pass `save_path=None` to return the `FuncAnimation` object without saving
(useful for interactive notebooks).

### `plot_timeseries` — checking the filter output

Before animating, verify the filter worked correctly with a time series plot:

```python
from el_nino.plots import plot_timeseries

fig = plot_timeseries(
    data=data,
    title="NINO1+2 SST — Fourier-filtered",
    ylabel="Temperature (°C)",
    save_path="data/output/sst_timeseries.png",
)
```

Only the original monthly grid points (irest == 0) are plotted. The filtered
temperature is shown in blue on the left y-axis; dT/dt is shown in red on the
right y-axis. El Niño events appear as blue peaks above the seasonal mean;
the corresponding dT/dt is positive during warming and negative during cooling.

### Reading the phase diagram: what El Niño looks like

In the phase diagram (T on x-axis, dT/dt on y-axis):

| Quadrant | T | dT/dt | ENSO state |
|----------|---|-------|------------|
| Upper right | high | positive | **El Niño developing** — temperature is warm and still rising |
| Lower right | high | negative | **El Niño decaying** — temperature is warm but cooling |
| Lower left | low | negative | **La Niña developing** — temperature is cool and still falling |
| Upper left | low | positive | **La Niña decaying** — temperature is cool but warming |

Strong El Niño events (1982–83, 1997–98, 2015–16) appear as large loops that
sweep far into the upper-right quadrant. The size of the loop in phase space
correlates with event intensity.

### Reading the phase diagram: what La Niña looks like

La Niña events appear as loops in the lower-left quadrant (cool, cooling). They
are typically weaker than El Niño events (smaller loops) but more persistent —
reflecting the asymmetry of the ENSO cycle. In the western Pacific stations
(Palau), La Niña produces the large excursions while El Niño events are
relatively small.

---

## 7. Working with config.yaml

The full pipeline reads all parameters from `config.yaml`:

```yaml
filter:
  HN1: 10.0   # low cutoff period (months) — long periods pass through
  HN2: 9.0    # high cutoff period (months) — short periods are removed
  NDOTS: 5    # interpolation sub-points per monthly interval

sst:
  local_file: "data/input/sst1950_1981.txt"
  ano_inicio: 1975         # first year to include from the local file
  noaa_url: "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"

stations:
  callao:
    id: "093"
    name: "Callao"
    start_date: "1905-01-01"
    xlim: [-300, 300]
    ylim: [-60, 60]
```

### How to add a new UHSLC station

1. Look up the UHSLC station ID at https://uhslc.soest.hawaii.edu/stations/
2. Add a block under `stations:` in config.yaml:

```yaml
stations:
  sydney:
    id: "111"
    name: "Sydney"
    start_date: "1886-01-01"
    xlim: [-200, 200]
    ylim: [-40, 40]
```

3. Run `pipeline.run_all("config.yaml")` — the new station is picked up
   automatically. `animate_all_from_config` also reads `xlim`/`ylim` from
   config, so no code changes are needed.

### How to change the filter cutoff

Edit `HN1` and `HN2` in config.yaml. To investigate ENSO on longer timescales:

```yaml
filter:
  HN1: 18.0   # pass periods longer than 18 months
  HN2: 15.0   # suppress periods shorter than 15 months
  NDOTS: 5
```

Re-run `run_all` and the output filenames will include the new cutoffs. Note
that decreasing HN1 below 12 months will start to suppress the annual cycle,
which is normally kept in the passband.

### How to change the start year

The `ano_inicio` key controls which years of the local historical file are
included. To start from 1950 (the earliest available data):

```yaml
sst:
  local_file: "data/input/sst1950_1981.txt"
  ano_inicio: 1950
```

---

## 8. Running All Stations

The convenience script `scripts/run_sst_test.py` runs a complete end-to-end
test on SST only:

```bash
source venv/bin/activate
python scripts/run_sst_test.py
```

Expected output:

```
=== Running SST pipeline ===
  Downloading SST from NOAA: https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices
  SST: 602 months  (1975/01 → 2025/02)
  NT = 602
  SIGMA30 = 0.3842
  SIGMA04 = 0.3619
  Written: data/output/sst_test.dat  (3006 interpolated points)

Phase diagram saved: data/output/sst_phase_diagram.png
Time series saved:   data/output/sst_timeseries.png
```

To run all four pipelines and produce animations, use `run_all` from Python
(the `scripts/run_all.py` stub is ready for your own extension):

```python
from el_nino.pipeline import run_all
from el_nino.plots import animate_all_from_config

run_all("config.yaml")
animate_all_from_config("config.yaml")
```

Expected output files after a complete run:

```
data/output/
├── sva.2_filter_10_9_1975.2_2025.4_SAIDApy.dat    # SST filter output
├── sva.2_filter_Callao_SAIDApy.dat
├── sva.2_filter_Honolulu_SAIDApy.dat
├── sva.2_filter_Palau_SAIDApy.dat
├── animation_SST_filter_10_9.mp4
├── animation_Callao_filter_10_9.mp4
├── animation_Honolulu_filter_10_9.mp4
└── animation_Palau_filter_10_9.mp4
```

---

## 9. The Fortran Verification Test

The original analysis was written in Fortran 77. The Python package is a
faithful translation of `filterfouriergr197501_202502.f`. Numerical
equivalence is verified by an automated test suite.

**Running the tests:**

```bash
source venv/bin/activate
python -m pytest tests/test_filter_vs_fortran.py -v -s
```

**What the three tests check:**

| Test | What it verifies | Pass condition |
|------|-----------------|----------------|
| `test_python_matches_fortran` | End-to-end: compile Fortran, run both programs on identical 5-year synthetic input, compare output column by column | max\|ΔT\| < 0.01°C, max\|ΔdT\| < 0.01°C/month |
| `test_filter_preserves_low_frequency` | 17-month mode (passband) amplitude ratio and 3-month mode (stopband) ratio | ratio > 0.9 and ratio < 0.1 respectively |
| `test_deri_fourier_derivative_accuracy` | VST from `deri_fourier` matches the analytical derivative of an exact Fourier mode at interior grid points | relative error < 1% |

The Fortran test is automatically skipped if gfortran is not installed. Install
it with `brew install gcc` (macOS) or `apt install gfortran` (Ubuntu/Debian).

**What the 0.005°C tolerance means:**
The Fortran output is written in F7.2 format (2 decimal places), which rounds
every value to the nearest 0.01. The maximum observed difference between the
Python and Fortran outputs is 0.005°C — half a rounding unit — which is
consistent with both programs computing the same result and the Fortran simply
rounding it before writing.

---

## 10. Variable Reference

| Variable | Physical meaning | Units | Where set |
|----------|-----------------|-------|-----------|
| `SST0` | Raw NINO1+2 SST | °C | `load_sst` |
| `SL0` | Raw monthly mean sea level | mm | `load_sea_level` |
| `ANUAL[m]` | Monthly climatological mean (m = 1..12) | °C or mm | `_compute_climatology` |
| `SST1` | Anomaly: SST0 − ANUAL[MES] | °C | `_run_pipeline_steps` |
| `SST2` | Low-pass filtered anomaly: `passa_baixa(SST1)` | °C | `_run_pipeline_steps` |
| `SST3` | Filtered series with seasonal cycle restored: SST2 + ANUAL[MES] | °C | `_run_pipeline_steps` |
| `SST4` / `T` | Fine-grid interpolated SST: `deri_fourier` output | °C | `deri_fourier` |
| `VST` / `dT` | First derivative dT/dt at fine-grid points | °C/month | `deri_fourier` |
| `AST` | Second derivative d²T/dt² (not written to output) | °C/month² | `deri_fourier` |
| `SIGMA30` | RMS(SST3 − SST0): filter residual | °C or mm | `compute_sigma` |
| `SIGMA04` | RMS(SST0 − SST4[::NDOTS]): interpolation residual at monthly pts | °C or mm | `compute_sigma` |
| `HN1` | Low-pass filter long-period edge | months | `config.yaml` |
| `HN2` | Low-pass filter short-period edge | months | `config.yaml` |
| `NDOTS` | Sub-divisions per monthly interval | — | `config.yaml` |
| `NT` | Number of monthly input points | — | computed from data length |
| `NM1` | NT − 1 (number of intervals) | — | `filter.py` |
| `NTD` | Number of fine-grid output points: (NT−1)×NDOTS + 1 | — | `deri_fourier` |
| `IYR` | Calendar year for each input point | — | `load_sst`, `load_sea_level` |
| `MES` | Calendar month (1..12) for each input point | — | `load_sst`, `load_sea_level` |
| `irest` | Sub-month index in output file (0 = original monthly point) | — | `_write_dat` |
| `IOLD` | Index of the parent monthly point for each fine-grid point | — | `_write_dat` |
| `W0`, `W1`, `W2` | Sigmoid window centre and edges in mode-number space | — | `passa_baixa` |
| `FOURIER[IW]` | Sine Fourier coefficient for mode IW | °C or mm | `passa_baixa`, `deri_fourier` |
| `FACTOR[IW]` | Sigmoid filter gain for mode IW | — | `passa_baixa` |

---

## 11. Common Recipes

### Recipe 1 — Plot phase diagram for a specific year range

```python
from el_nino.pipeline import load_output
from el_nino.plots import plot_phase_diagram
import numpy as np

data = load_output("data/output/sst_filtered.dat")

# Restrict to 1990–2005 by masking on the year array.
mask = (data["year"] >= 1990) & (data["year"] <= 2005)
subset = {k: v[mask] for k, v in data.items()}

fig = plot_phase_diagram(
    subset, "NINO1+2 SST 1990–2005",
    "Temperature (°C)", [17.5, 32.5], [-2.5, 2.5],
    save_path="data/output/sst_1990_2005.png",
)
```

### Recipe 2 — Compare SST and Callao attractors side by side

```python
import matplotlib.pyplot as plt
from el_nino.pipeline import load_output
from el_nino.plots import _prepare_xy

sst_data = load_output("data/output/sva.2_filter_10_9_1975.2_2025.4_SAIDApy.dat")
sl_data  = load_output("data/output/sva.2_filter_Callao_SAIDApy.dat")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

x_sst, y_sst = _prepare_xy(sst_data, remove_mean=False)
ax1.plot(x_sst, y_sst, color="steelblue", linewidth=0.5, alpha=0.7)
ax1.set_title("NINO1+2 SST"); ax1.set_xlabel("°C"); ax1.set_ylabel("dT/dt")
ax1.axvline(0); ax1.axhline(0); ax1.grid(True, alpha=0.4)

x_sl, y_sl = _prepare_xy(sl_data, remove_mean=True)
ax2.plot(x_sl, y_sl, color="firebrick", linewidth=0.5, alpha=0.7)
ax2.set_title("Callao sea level"); ax2.set_xlabel("mm anomaly"); ax2.set_ylabel("dSL/dt")
ax2.axvline(0); ax2.axhline(0); ax2.grid(True, alpha=0.4)

fig.tight_layout()
fig.savefig("data/output/comparison.png", dpi=150, bbox_inches="tight")
```

### Recipe 3 — Highlight the 1997–98 El Niño event

```python
from el_nino.pipeline import load_output
import matplotlib.pyplot as plt
import numpy as np

data = load_output("data/output/sst_filtered.dat")
x, y = data["T"], data["dT"]
year, month = data["year"], data["month"]

fig, ax = plt.subplots(figsize=(8, 6))
ax.plot(x, y, color="lightgray", linewidth=0.8, zorder=1)

# Highlight the 1997-04 to 1998-06 period (peak El Niño)
mask = ((year == 1997) & (month >= 4)) | (year == 1998) & (month <= 6)
ax.plot(x[mask], y[mask], color="red", linewidth=2.5, zorder=2,
        label="1997–98 El Niño")

ax.set_title("NINO1+2 SST Phase Diagram — 1997–98 highlighted")
ax.set_xlabel("Temperature (°C)"); ax.set_ylabel("dT/dt (°C/month)")
ax.set_xlim(17.5, 32.5); ax.set_ylim(-2.5, 2.5)
ax.axvline(0, linestyle="--", color="black", alpha=0.6)
ax.axhline(0, linestyle="--", color="black", alpha=0.6)
ax.legend(); ax.grid(True, alpha=0.5)
fig.savefig("data/output/1997_elnino.png", dpi=150)
```

### Recipe 4 — Add a new UHSLC station (Sydney, station 111)

1. Add to `config.yaml`:

```yaml
stations:
  sydney:
    id: "111"
    name: "Sydney"
    start_date: "1886-01-01"
    xlim: [-200, 200]
    ylim: [-40, 40]
```

2. Run the pipeline — no code changes needed:

```python
from el_nino.pipeline import run_all
results = run_all("config.yaml")
print(f"Sydney NT = {len(results['sydney']['SL0'])}")
```

### Recipe 5 — Change the filter cutoff and compare results

```python
from el_nino.filter import passa_baixa, deri_fourier
from el_nino.pipeline import load_output
from el_nino.download import load_sst
import matplotlib.pyplot as plt
import numpy as np

raw = load_sst("data/input/sst1950_1981.txt", ano_inicio=1975)
SST0, MES = raw["SST0"], raw["MES"]
clim = np.array([SST0[MES == m].mean() for m in range(1, 13)])
anomaly = SST0 - clim[MES - 1]

fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
for ax, (HN1, HN2) in zip(axes, [(10, 9), (18, 15), (6, 5)]):
    filtered = passa_baixa(HN1, HN2, anomaly)
    sst, vst, _ = deri_fourier(5, filtered + clim[MES - 1])
    ax.plot(sst, vst, color="steelblue", linewidth=0.5, alpha=0.7)
    ax.set_title(f"HN1={HN1}, HN2={HN2} months")
    ax.set_xlabel("SST (°C)"); ax.axvline(0); ax.axhline(0)
axes[0].set_ylabel("dT/dt (°C/month)")
fig.tight_layout()
fig.savefig("data/output/filter_comparison.png", dpi=150)
```
