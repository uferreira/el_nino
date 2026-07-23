"""
el_nino.pipeline
================
Orchestration: connects download → filter → output file.

Each public function runs one complete dataset through the five-step
pipeline that mirrors the reference Fortran program:

    1. Load monthly time series (SST or sea level)
    2. Compute monthly climatology and remove seasonal cycle
    3. Apply Fourier low-pass filter (passa_baixa)
    4. Re-add seasonal cycle
    5. Fourier-interpolate to fine grid and compute derivatives (deri_fourier)
    6. Write output .dat file in the Fortran format 5766

The functions in this module never re-implement the mathematics — they
delegate entirely to el_nino.filter and el_nino.download.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from el_nino import download
from el_nino.filter import compute_sigma, deri_fourier, passa_baixa


# ---------------------------------------------------------------------------
# Private helpers shared by run_sst and run_sea_level
# ---------------------------------------------------------------------------

def _align_fourier_window(
    IYR: np.ndarray,
    MES: np.ndarray,
    data: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Start the Fourier window in the same calendar month in which it ends.

    The sine-series detrending in the translated Fortran algorithm uses the
    first and last values as its boundary.  Keeping a fixed January start as
    new observations advance through the year therefore joins different
    phases of the seasonal cycle (for example January to July).  The original
    Fortran input avoided that jump by using matching endpoint months.

    Select the earliest observation whose calendar month matches the latest
    observation and discard only the leading partial seasonal cycle (at most
    eleven observations for a continuous monthly record).  No synthetic value
    is introduced and the most recent observation is always retained.
    """
    IYR = np.asarray(IYR)
    MES = np.asarray(MES)
    data = np.asarray(data)

    if not (len(IYR) == len(MES) == len(data)):
        raise ValueError("IYR, MES, and data must have the same length")
    if len(MES) < 2:
        raise ValueError("at least two monthly observations are required")
    if np.any((MES < 1) | (MES > 12)):
        raise ValueError("MES values must be calendar months in 1..12")

    terminal_month = int(MES[-1])
    start = int(np.flatnonzero(MES == terminal_month)[0])
    return IYR[start:], MES[start:], data[start:]


def _compute_climatology(MES: np.ndarray, data: np.ndarray) -> np.ndarray:
    """
    Compute the mean value for each calendar month.

    Parameters
    ----------
    MES  : int32 array of shape (NT,) — month index 1..12
    data : float64 array of shape (NT,) — the raw time series

    Returns
    -------
    clim : float64 array of shape (12,), indexed 0..11
        clim[0] = mean over all January values, clim[1] = February, …
    """
    # Vectorised groupby-mean is more readable and faster than a loop,
    # and avoids a dependency on pandas here in the filter layer.
    return np.array([data[MES == m].mean() for m in range(1, 13)])


def _run_pipeline_steps(
    raw: np.ndarray,
    MES: np.ndarray,
    HN1: float,
    HN2: float,
    NDOTS: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """
    Apply the complete filter pipeline to a raw monthly series.

    This is the mathematical core shared by run_sst and run_sea_level.
    Separating it from I/O makes unit-testing straightforward.

    Steps
    -----
    1. Compute monthly climatology ANUAL[0..11].
    2. Remove seasonal cycle → anomaly.
    3. passa_baixa on anomaly → filtered anomaly.
    4. Re-add seasonal cycle → full filtered series.
    5. deri_fourier → interpolated series + derivatives.
    6. compute_sigma → diagnostic RMS values.

    Parameters
    ----------
    raw   : float64 array (NT,) — raw monthly observations
    MES   : int32 array (NT,)   — month indices 1..12
    HN1   : float — low-frequency filter cutoff (months)
    HN2   : float — high-frequency filter cutoff (months)
    NDOTS : int   — sub-divisions per monthly interval

    Returns
    -------
    filtered  : float64 (NT,)  — low-pass filtered series with seasonal cycle
    interp    : float64 (NTD,) — interpolated series (NTD = (NT-1)*NDOTS + 1)
    vel       : float64 (NTD,) — first derivative dT/dt
    accel     : float64 (NTD,) — second derivative d²T/dt²
    sigma30   : float — RMS(filtered − raw)
    sigma04   : float — RMS(raw − interp[::NDOTS])
    """
    # Monthly climatology (12 values, 0-indexed).
    clim = _compute_climatology(MES, raw)

    # Broadcast the per-month mean to the full time axis.
    clim_monthly = clim[MES - 1]

    # Remove the seasonal cycle so the filter operates on anomalies.
    # Reason: the 12-month harmonic, if left in, would dominate the Fourier
    # spectrum and cause spectral leakage from the seasonal band into the
    # ENSO band even though 12 months lies within the passband (> HN1=10).
    # Removing the sample mean per month also correctly handles non-sinusoidal
    # seasonal shapes (e.g. asymmetric warming/cooling cycles).
    anomaly = raw - clim_monthly

    # Low-pass filter on the anomaly (removes variability faster than ~HN2).
    filtered_anomaly = passa_baixa(HN1, HN2, anomaly)

    # Re-add the seasonal cycle so the output represents absolute values.
    # This preserves the seasonal swing in the phase-space trajectory
    # (T vs dT/dt), making El Niño warm phases visually distinct from
    # the annual warm season.
    filtered = filtered_anomaly + clim_monthly

    # Fourier-interpolate to NDOTS sub-points per month and compute dT/dt.
    interp, vel, accel = deri_fourier(NDOTS, filtered)

    # Diagnostic RMS errors — printed by the caller, mirroring the Fortran's
    # WRITE(6,1795) and WRITE(6,1296) output lines.
    sigma30, sigma04 = compute_sigma(raw, filtered, interp, NDOTS)

    return filtered, interp, vel, accel, sigma30, sigma04


def _write_dat(
    output_file: str,
    T_arr: np.ndarray,
    V_arr: np.ndarray,
    IYR: np.ndarray,
    MES: np.ndarray,
    NDOTS: int,
) -> None:
    """
    Write the output .dat file in the exact Fortran format 5766.

    Each line corresponds to one sub-monthly interpolated point:

        ' F7.2;F7.2;I5;I3;I2'

    where the columns are: T ; dT/dt ; year ; month ; IREST.

    IREST is the sub-month index (0 = original monthly point, 1..NDOTS-1 =
    interpolated sub-points). IREST=0 rows correspond to IOLD-th month in
    the input series.

    Parameters
    ----------
    output_file : str — destination path (parent directory is created if absent)
    T_arr  : fine-grid interpolated series (NTD,)
    V_arr  : fine-grid first derivative    (NTD,)
    IYR    : original years   (NT,)
    MES    : original months  (NT,)
    NDOTS  : sub-divisions per month
    """
    NT  = len(IYR)
    NTD = (NT - 1) * NDOTS + 1

    # Create the output directory hierarchy if it does not exist.
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as fout:
        # I is 1-based, matching the Fortran loop DO 7788 I=1,NM1*NDOTS+1.
        for I in range(1, NTD + 1):
            # Which original monthly point does this sub-point belong to?
            IOLD  = 1 + (I - 1) // NDOTS
            # IREST=0 marks the original monthly grid point; 1..NDOTS-1 are
            # the interpolated sub-points that lie between two monthly obs.
            IREST = I - (IOLD - 1) * NDOTS - 1

            # IOLD never exceeds NT for valid I, but the guard is kept to
            # match the Fortran's defensive yr=0 / mon=0 fallback.
            if IOLD <= NT:
                yr  = int(IYR[IOLD - 1])
                mon = int(MES[IOLD - 1])
            else:
                yr  = 0
                mon = 0

            fout.write(
                f" {T_arr[I - 1]:7.2f};{V_arr[I - 1]:7.2f}"
                f";{yr:5d};{mon:3d};{IREST:2d}\n"
            )


# ---------------------------------------------------------------------------
# Public pipeline functions
# ---------------------------------------------------------------------------

def run_sst(
    local_file: str,
    ano_inicio: int,
    HN1: float,
    HN2: float,
    NDOTS: int,
    output_file: str,
) -> dict:
    """
    Full SST pipeline: raw data → Fourier filter → output .dat file.

    Loads NINO1+2 SST from the local historical file and the NOAA CPC
    live download, applies the Fourier low-pass filter, and writes the
    interpolated output in the Fortran format used by the phase-diagram
    animation code.

    Seasonal cycle treatment
    ------------------------
    The pipeline removes the monthly climatological mean (ANUAL[0..11])
    before filtering and re-adds it afterwards.  The reason is that the
    Fourier filter operates most cleanly on anomalies:

    * Even though the 12-month annual harmonic is in the passband
      (12 months > HN1 = 10 months), leaving it in creates a dominant
      spectral peak that can leak into adjacent low-frequency modes via
      the finite-sample Fourier expansion.
    * The climatological subtraction also handles non-sinusoidal seasonal
      patterns (the tropical SST cycle is not a pure sine) without
      assumptions about its shape.
    * Re-adding the cycle after filtering preserves the absolute SST level,
      so the phase-diagram trajectory (T vs dT/dt) shows the actual warm
      and cold phases of ENSO superimposed on the seasonal cycle.

    Parameters
    ----------
    local_file  : str   — path to local historical SST file (1950–1981)
    ano_inicio  : int   — first year to use from the local file
    HN1         : float — long-period edge of the filter transition band (months)
    HN2         : float — short-period edge of the filter transition band (months)
    NDOTS       : int   — interpolation sub-points per monthly interval
    output_file : str   — path for the output .dat file

    Returns
    -------
    dict with keys:
        IYR     : int32 array   — years of the input series
        MES     : int32 array   — months of the input series
        SST0    : float64 array — raw NINO1+2 SST (°C)
        SST3    : float64 array — filtered SST with seasonal cycle (°C)
        SST4    : float64 array — fine-grid interpolated SST (°C)
        VST     : float64 array — fine-grid dSST/dt (°C/month)
        sigma30 : float         — RMS filter residual (°C)
        sigma04 : float         — RMS interpolation residual at monthly pts (°C)
        output_file : str       — path of the written file
    """
    # --- Load data ---
    raw_data = download.load_sst(local_file=local_file, ano_inicio=ano_inicio)
    IYR  = raw_data["IYR"]
    MES  = raw_data["MES"]
    SST0 = raw_data["SST0"]
    IYR, MES, SST0 = _align_fourier_window(IYR, MES, SST0)
    NT   = len(SST0)
    print(f"  NT = {NT}")

    # --- Filter pipeline ---
    SST3, SST4, VST, AST, sigma30, sigma04 = _run_pipeline_steps(
        SST0, MES, HN1, HN2, NDOTS
    )
    print(f"  SIGMA30 = {sigma30:.4f}")
    print(f"  SIGMA04 = {sigma04:.4f}")

    # --- Write output ---
    _write_dat(output_file, SST4, VST, IYR, MES, NDOTS)
    NTD = (NT - 1) * NDOTS + 1
    print(f"  Written: {output_file}  ({NTD} interpolated points)")

    return {
        "IYR":         IYR,
        "MES":         MES,
        "SST0":        SST0,
        "SST3":        SST3,
        "SST4":        SST4,
        "VST":         VST,
        "sigma30":     sigma30,
        "sigma04":     sigma04,
        "output_file": output_file,
    }


def run_sst_index(
    index_key: str,
    local_file: str,
    ano_inicio: int,
    HN1: float,
    HN2: float,
    NDOTS: int,
    output_file: str,
) -> dict:
    """
    Pipeline for a single SST anomaly index (NINO12, NINO3, NINO4, NINO34).

    Unlike run_sst, this function operates on the pre-computed anomaly column
    (already deseasonalized by NOAA), so it skips the climatology subtraction
    step and feeds the anomaly directly to passa_baixa.

    Parameters
    ----------
    index_key   : str  — one of "nino12", "nino3", "nino4", "nino34"
    local_file  : str  — path to local historical SST file
    ano_inicio  : int  — first year to use
    HN1, HN2    : float — filter band edges (months)
    NDOTS       : int  — interpolation sub-points per monthly interval
    output_file : str  — path for the output .dat file

    Returns
    -------
    dict with keys: IYR, MES, ANOM, filtered, interp, vel, sigma30, sigma04,
    output_file
    """
    _anom_key_map = {
        "nino12": "ANOM12",
        "nino3":  "ANOM3",
        "nino4":  "ANOM4",
        "nino34": "ANOM34",
    }
    anom_key = _anom_key_map.get(index_key)
    if anom_key is None:
        raise ValueError(f"Unknown SST index key: {index_key!r}")

    raw_data = download.load_sst(local_file=local_file, ano_inicio=ano_inicio)
    IYR  = raw_data["IYR"]
    MES  = raw_data["MES"]
    anom = raw_data[anom_key]
    IYR, MES, anom = _align_fourier_window(IYR, MES, anom)
    NT   = len(anom)
    print(f"  NT = {NT}")

    filtered_anom = passa_baixa(HN1, HN2, anom)
    interp, vel, accel = deri_fourier(NDOTS, filtered_anom)
    sigma30, sigma04 = compute_sigma(anom, filtered_anom, interp, NDOTS)
    print(f"  SIGMA30 = {sigma30:.4f}")
    print(f"  SIGMA04 = {sigma04:.4f}")

    _write_dat(output_file, interp, vel, IYR, MES, NDOTS)
    NTD = (NT - 1) * NDOTS + 1
    print(f"  Written: {output_file}  ({NTD} interpolated points)")

    return {
        "IYR":         IYR,
        "MES":         MES,
        "ANOM":        anom,
        "filtered":    filtered_anom,
        "interp":      interp,
        "vel":         vel,
        "sigma30":     sigma30,
        "sigma04":     sigma04,
        "output_file": output_file,
    }


def run_sea_level(
    station_id: str,
    station_name: str,
    start_date: str,
    HN1: float,
    HN2: float,
    NDOTS: int,
    output_file: str,
    rqd_url: str | None = None,
) -> dict:
    """
    Full sea level pipeline: raw data → Fourier filter → output .dat file.

    Identical in structure to run_sst: downloads hourly sea level from
    UHSLC ERDDAP, aggregates to monthly, applies the Fourier low-pass
    filter with seasonal-cycle removal, and writes the interpolated output.

    The seasonal cycle removal is equally important for sea level: the
    annual steric and wind-driven sea level cycle (typically 10–30 cm
    peak-to-peak in the tropical Pacific) is a strong 12-month signal
    that would dominate the Fourier spectrum if left in, potentially
    leaking energy into the ENSO band.

    Parameters
    ----------
    station_id   : str   — UHSLC 3-digit station ID (e.g. "093")
    station_name : str   — human-readable station name (e.g. "Callao")
    start_date   : str   — ISO 8601 date string for start of download window
    HN1          : float — long-period filter edge (months)
    HN2          : float — short-period filter edge (months)
    NDOTS        : int   — interpolation sub-points per monthly interval
    output_file  : str   — path for the output .dat file

    Returns
    -------
    dict with keys:
        IYR     : int32 array   — years of the input series
        MES     : int32 array   — months of the input series
        SL0     : float64 array — raw monthly mean sea level (mm)
        SL3     : float64 array — filtered sea level with seasonal cycle (mm)
        SL4     : float64 array — fine-grid interpolated sea level (mm)
        VST     : float64 array — fine-grid dSL/dt (mm/month)
        sigma30 : float         — RMS filter residual (mm)
        sigma04 : float         — RMS interpolation residual at monthly pts (mm)
        output_file : str       — path of the written file
    """
    # --- Load data ---
    raw_data = download.load_sea_level(
        station_id=station_id,
        station_name=station_name,
        start_date=start_date,
        rqd_url=rqd_url,
    )
    IYR = raw_data["IYR"]
    MES = raw_data["MES"]
    SL0 = raw_data["SL0"]
    IYR, MES, SL0 = _align_fourier_window(IYR, MES, SL0)
    NT  = len(SL0)
    print(f"  NT = {NT}")

    # --- Filter pipeline (same steps as SST) ---
    SL3, SL4, VST, AST, sigma30, sigma04 = _run_pipeline_steps(
        SL0, MES, HN1, HN2, NDOTS
    )
    print(f"  SIGMA30 = {sigma30:.4f}")
    print(f"  SIGMA04 = {sigma04:.4f}")

    # --- Write output ---
    _write_dat(output_file, SL4, VST, IYR, MES, NDOTS)
    NTD = (NT - 1) * NDOTS + 1
    print(f"  Written: {output_file}  ({NTD} interpolated points)")

    return {
        "IYR":         IYR,
        "MES":         MES,
        "SL0":         SL0,
        "SL3":         SL3,
        "SL4":         SL4,
        "VST":         VST,
        "sigma30":     sigma30,
        "sigma04":     sigma04,
        "output_file": output_file,
    }


def run_all(config_path: str = "config.yaml") -> dict:
    """
    Run all four pipelines (SST + 3 sea level stations) from config.yaml.

    Reads filter parameters, data-source configuration, and station
    metadata from config.yaml, then calls run_sst and run_sea_level for
    each dataset.  Output .dat files are written to data/output/ with
    names matching the Fortran convention.

    Output filename conventions
    ---------------------------
    SST:
        data/output/sva.2_filter_{HN1}_{HN2}_{yr0}.{m0}_{yr1}.{m1}_SAIDApy.dat
        where yr0/m0 and yr1/m1 are the start and end of the data series.

    Sea level:
        data/output/sva.2_filter_{station_name}_SAIDApy.dat

    Parameters
    ----------
    config_path : str
        Path to the YAML configuration file.  Defaults to "config.yaml"
        in the current working directory.

    Returns
    -------
    dict with keys:
        "sst_nino12"  : dict from run_sst (NINO1+2 absolute SST)
        "sst_nino3"   : dict from run_sst_index (NINO3 anomaly)
        "sst_nino4"   : dict from run_sst_index (NINO4 anomaly)
        "sst_nino34"  : dict from run_sst_index (NINO3.4 anomaly)
        "<station_key>": dict from run_sea_level for each station in config

    Raises
    ------
    FileNotFoundError
        If config_path does not exist.
    KeyError
        If a required configuration key is absent.
    RuntimeError
        If any download or filter step fails.
    """
    with open(config_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    flt     = cfg["filter"]
    HN1     = float(flt["HN1"])
    HN2     = float(flt["HN2"])
    NDOTS   = int(flt["NDOTS"])
    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    sst_cfg = cfg["sst"]
    result  = {}

    # --- NINO1+2 absolute SST (Classic phase diagram) ---
    print("\n=== SST NINO1+2 pipeline (absolute) ===")
    nino12_path = out_dir / "sva.2_filter_NINO12_SAIDApy.dat"
    result["sst_nino12"] = run_sst(
        local_file=sst_cfg["local_file"],
        ano_inicio=sst_cfg["ano_inicio"],
        HN1=HN1,
        HN2=HN2,
        NDOTS=NDOTS,
        output_file=str(nino12_path),
    )
    result["sst_nino12"]["output_file"] = str(nino12_path)

    # --- Remaining SST indices (anomaly-based) ---
    for idx_cfg in cfg.get("sst_indices", []):
        key = idx_cfg["key"]
        if key == "nino12":
            continue  # handled above
        print(f"\n=== SST {idx_cfg['label']} pipeline (anomaly) ===")
        out_path = out_dir / f"sva.2_filter_{key.upper()}_SAIDApy.dat"
        result[f"sst_{key}"] = run_sst_index(
            index_key=key,
            local_file=sst_cfg["local_file"],
            ano_inicio=sst_cfg["ano_inicio"],
            HN1=HN1,
            HN2=HN2,
            NDOTS=NDOTS,
            output_file=str(out_path),
        )

    # --- Sea level stations ---
    for key, st in cfg["stations"].items():
        print(f"\n=== {st['name']} pipeline ===")
        out_path = out_dir / f"sva.2_filter_{st['name']}_SAIDApy.dat"
        result[key] = run_sea_level(
            station_id=st["id"],
            station_name=st["name"],
            start_date=st["start_date"],
            HN1=HN1,
            HN2=HN2,
            NDOTS=NDOTS,
            output_file=str(out_path),
            rqd_url=st.get("rqd_url"),
        )

    return result


def accel_from_raw(
    raw: np.ndarray,
    MES: np.ndarray,
    HN1: float,
    HN2: float,
    NDOTS: int,
) -> np.ndarray:
    """
    Compute the exact second derivative d²T/dt² from raw monthly data.

    Runs the full filter pipeline via _run_pipeline_steps and returns the
    AST (acceleration) array produced analytically by deri_fourier.  The
    result is numerically identical to the AST field returned by
    _run_pipeline_steps — no separate numerical differentiation is needed.

    Parameters
    ----------
    raw   : float64 array (NT,)  — raw monthly observations
    MES   : int32 array (NT,)    — month indices 1..12
    HN1   : float — long-period filter edge (months)
    HN2   : float — short-period filter edge (months)
    NDOTS : int   — sub-divisions per monthly interval

    Returns
    -------
    accel : float64 array (NTD,) — second derivative d²T/dt²
              where NTD = (NT-1)*NDOTS + 1
    """
    _, _, _, accel, _, _ = _run_pipeline_steps(raw, MES, HN1, HN2, NDOTS)
    return accel


def accel_from_output(data: dict) -> np.ndarray:
    """
    Estimate d²T/dt² by numerically differentiating the dT/dt column.

    Fallback for when only a .dat output file is available and no raw
    monthly data can be provided.  Uses numpy.gradient (second-order
    central differences) on data["dT"] with step size 1/NDOTS months.
    NDOTS is inferred from max(data["irest"]) + 1.

    Parameters
    ----------
    data : dict from load_output() — must contain keys "dT" and "irest"

    Returns
    -------
    accel : float64 array of the same length as data["dT"]
    """
    NDOTS = int(data["irest"].max()) + 1
    dt    = 1.0 / NDOTS
    return np.gradient(data["dT"], dt)


def load_with_accel(
    output_file: str,
    raw: np.ndarray | None = None,
    MES: np.ndarray | None = None,
    HN1: float = 10.0,
    HN2: float = 9.0,
    NDOTS: int = 5,
) -> dict:
    """
    Load a .dat file and augment the result with d²T/dt².

    If raw monthly data (raw, MES) are supplied, uses accel_from_raw for
    the analytically exact second derivative.  Otherwise falls back to
    accel_from_output (numerical differentiation of the dT column).

    Parameters
    ----------
    output_file : str — path to a .dat file from run_sst or run_sea_level
    raw  : float64 array (NT,) or None — raw monthly observations
    MES  : int32 array (NT,) or None   — month indices 1..12
    HN1  : float — long-period filter cutoff (months); used only with raw
    HN2  : float — short-period filter cutoff (months); used only with raw
    NDOTS: int   — sub-divisions per month; used only with raw

    Returns
    -------
    dict — all keys from load_output() plus:
        d2T : float64 array (NTD,) — second derivative d²T/dt²
    """
    data = load_output(output_file)
    if raw is not None and MES is not None:
        data["d2T"] = accel_from_raw(raw, MES, HN1, HN2, NDOTS)
    else:
        data["d2T"] = accel_from_output(data)
    return data


def load_output(output_file: str) -> dict:
    """
    Read a previously written .dat file back into NumPy arrays.

    This allows plots.py to reload filter results without re-running the
    full pipeline.  The file format is the Fortran 5766 semicolon-delimited
    layout written by _write_dat.

    Expected line format::

        ' F7.2;F7.2;I5;I3;I2'

    i.e.::

        '  25.37;   0.12; 1975;  2; 0'

    Parameters
    ----------
    output_file : str
        Path to the .dat file written by run_sst or run_sea_level.

    Returns
    -------
    dict with keys:
        T     : float64 array — interpolated temperature or sea level
        dT    : float64 array — rate of change dT/dt
        year  : int32 array   — calendar year for each sub-point
        month : int32 array   — calendar month (1..12) for each sub-point
        irest : int32 array   — sub-month index (0 = original monthly point)

    Raises
    ------
    FileNotFoundError
        If output_file does not exist.
    ValueError
        If the file contains no valid data lines.
    """
    T_list, dT_list, yr_list, mon_list, irest_list = [], [], [], [], []

    with open(output_file, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) < 5:
                continue
            try:
                T_list.append(float(parts[0]))
                dT_list.append(float(parts[1]))
                yr_list.append(int(parts[2]))
                mon_list.append(int(parts[3]))
                irest_list.append(int(parts[4]))
            except ValueError:
                continue

    if not T_list:
        raise ValueError(f"No valid data found in {output_file}")

    return {
        "T":     np.array(T_list,     dtype=np.float64),
        "dT":    np.array(dT_list,    dtype=np.float64),
        "year":  np.array(yr_list,    dtype=np.int32),
        "month": np.array(mon_list,   dtype=np.int32),
        "irest": np.array(irest_list, dtype=np.int32),
    }


# ---------------------------------------------------------------------------
# Self-test (no network, no file I/O)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Verify the filter pipeline with synthetic SST data.

    Signal: SST(t) = 25 + 2·sin(2π t/12) + 0.5·sin(2π t/36)
        seasonal component (12-month):   removed by climatology subtraction
        ENSO-like component (36-month):  passes the filter (36 > HN1=10)

    Because the seasonal and ENSO components are both either perfectly
    captured by the climatology or in the passband, sigma30 arises only
    from the imperfect Fourier-series approximation on a finite grid.
    The test verifies that the residual is finite and positive, that the
    output lengths are correct, and that the derivative changes sign.
    """
    print("Running self-test …")

    NT    = 120
    NDOTS = 5
    NTD   = (NT - 1) * NDOTS + 1     # expected interpolated length = 596
    t     = np.arange(NT, dtype=float)

    # Months cycle 1..12 for 10 complete years.
    MES_s = np.array([(i % 12) + 1 for i in range(NT)], dtype=np.int32)

    # Synthetic signal as specified: seasonal + ENSO-like.
    SST_s = (
        25.0
        + 2.0 * np.sin(2.0 * np.pi * t / 12.0)   # annual cycle
        + 0.5 * np.sin(2.0 * np.pi * t / 36.0)   # ENSO-like (3 years)
    )

    # Run the shared pipeline helper (no download, no file I/O).
    SST3, SST4, VST, AST, sigma30, sigma04 = _run_pipeline_steps(
        SST_s, MES_s, HN1=10.0, HN2=9.0, NDOTS=NDOTS
    )

    # --- 1. SST4 has the correct interpolated length ---
    assert len(SST4) == NTD, (
        f"FAIL 1: SST4 length = {len(SST4)}, expected {NTD}"
    )
    print(f"  PASS 1: SST4 length = {NTD}  (= (NT-1)×NDOTS + 1 = 119×5 + 1)")

    # --- 2. sigma30 > 0 ---
    # Even with no explicit high-frequency component, the finite Fourier
    # expansion on a non-periodic finite interval introduces a small but
    # strictly positive reconstruction residual.
    assert sigma30 > 0, f"FAIL 2: sigma30 = {sigma30:.2e}  (expected > 0)"
    print(f"  PASS 2: sigma30 > 0  (sigma30 = {sigma30:.6f})")

    # --- 3. sigma04 < sigma30 ---
    # deri_fourier reconstructs SST3 faithfully using all its Fourier modes
    # (no sigmoid attenuation), so the interpolation error at original monthly
    # points is smaller than the filter residual.
    assert sigma04 < sigma30, (
        f"FAIL 3: sigma04 ({sigma04:.6f}) >= sigma30 ({sigma30:.6f})"
    )
    print(f"  PASS 3: sigma04 < sigma30  "
          f"(sigma04 = {sigma04:.6f}, sigma30 = {sigma30:.6f})")

    # --- 4. VST changes sign ---
    # The derivative of an oscillating signal must cross zero — a constant
    # VST would indicate a bug in deri_fourier or _run_pipeline_steps.
    assert np.any(VST > 0) and np.any(VST < 0), (
        "FAIL 4: VST does not change sign"
    )
    print(f"  PASS 4: VST changes sign  "
          f"(min = {VST.min():.4f}, max = {VST.max():.4f})")

    # --- 5. accel_from_raw matches _run_pipeline_steps AST exactly ---
    accel = accel_from_raw(SST_s, MES_s, HN1=10.0, HN2=9.0, NDOTS=NDOTS)
    assert len(accel) == NTD, (
        f"FAIL 5: accel_from_raw length = {len(accel)}, expected {NTD}"
    )
    assert np.allclose(accel, AST, rtol=0, atol=0), (
        "FAIL 5: accel_from_raw does not match _run_pipeline_steps AST"
    )
    print(
        f"  PASS 5: accel_from_raw == AST exactly  "
        f"(max diff = {float(np.max(np.abs(accel - AST))):.2e})"
    )

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
