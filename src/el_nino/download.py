"""
el_nino.download
================
Data acquisition: SST from NOAA CPC and hourly sea level from UHSLC ERDDAP.

All public functions return plain dicts of NumPy arrays so callers have no
dependency on pandas beyond this module boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import numpy as np
import pandas as pd
import requests
import yaml

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

NOAA_SST_URL = "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"

# UHSLC ERDDAP Fast Delivery endpoint — returns CSV with two header rows.
ERDDAP_BASE = (
    "https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv"
)

# UHSLC encodes missing observations as -32767 (short int sentinel, not NaN).
FILL_VALUE = -32767

REQUEST_TIMEOUT = 60   # seconds; ERDDAP for long series can be slow

# Column order shared by both the local historical file and the NOAA online file.
_SST_COLS = [
    "YR", "MON",
    "NINO12", "ANOM12",
    "NINO3",  "ANOM3",
    "NINO4",  "ANOM4",
    "NINO34", "ANOM34",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, label: str) -> requests.Response:
    """
    Perform a GET request and return the response.

    Wraps network errors in a RuntimeError with a human-readable message
    that includes the URL — useful when the failure is deep in a pipeline.
    """
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Timeout after {REQUEST_TIMEOUT}s downloading {label}.\n"
            f"URL: {url}"
        ) from None
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"HTTP {exc.response.status_code} downloading {label}.\n"
            f"URL: {url}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Network error downloading {label}: {exc}"
        ) from exc


def _snap_to_hour(series: pd.Series) -> pd.Series:
    """
    Round timestamps that are within 5 minutes of a full clock hour.

    UHSLC ERDDAP frequently delivers observations at 04:59:59 or 05:00:01
    instead of exactly 05:00:00. Without this correction, two observations
    from the same clock hour would survive into the monthly aggregation,
    inflating or randomly biasing the monthly mean.

    Timestamps more than 5 minutes from the nearest hour are left unchanged
    to avoid silently re-labelling sub-hourly data.
    """
    mins = series.dt.minute
    out  = series.copy()
    # Snap xx:55–xx:59 up to the next full hour.
    out.loc[mins >= 55] = out.loc[mins >= 55].dt.ceil("h")
    # Snap xx:00–xx:05 down to the current full hour.
    out.loc[mins <= 5]  = out.loc[mins <= 5].dt.floor("h")
    return out


def _clean_obs(series: pd.Series) -> pd.Series:
    """
    Coerce non-numeric strings to NaN and replace the UHSLC fill sentinel.

    The UHSLC format uses −32767 (the minimum signed 16-bit integer) as
    its missing-data code. Replacing it with NaN before aggregation ensures
    that missing hours do not drag down monthly means.
    """
    return pd.to_numeric(series, errors="coerce").replace(FILL_VALUE, np.nan)


def _parse_sst_lines(lines: list[str], ano_inicio: int) -> pd.DataFrame:
    """
    Parse lines from a NOAA SST index file into a DataFrame.

    Both the local historical file and the NOAA online file share the
    same whitespace-delimited format with one header line followed by
    data lines of exactly 10 fields:

        YR MON NINO12 ANOM12 NINO3 ANOM3 NINO4 ANOM4 NINO34 ANOM34

    Lines with fewer than 10 fields or a non-numeric year are silently
    skipped rather than raising an exception, matching the Fortran
    program's behaviour of reading until EOF without explicit validation.

    Parameters
    ----------
    lines : list[str]
        Raw text lines (including the header at index 0).
    ano_inicio : int
        Skip data lines whose year is before this value.
    """
    rows = []
    for i, line in enumerate(lines):
        # Line 0 is always the column header in both file variants.
        if i == 0:
            continue
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            yr  = int(parts[0])
            mon = int(parts[1])
        except ValueError:
            # Non-numeric year/month signals end of data or a comment line.
            continue
        if yr < ano_inicio:
            continue
        try:
            vals = [float(v) for v in parts[2:10]]
        except ValueError:
            continue
        rows.append([yr, mon] + vals)
    return pd.DataFrame(rows, columns=_SST_COLS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_sst(
    local_file: str = "data/input/sst1950_1981.txt",
    ano_inicio: int = 1975,
) -> dict:
    """
    Load monthly NINO1+2 SST by combining a local historical file with a
    live download from NOAA CPC.

    Data sources
    ------------
    Local file (1950–1981)
        NOAA legacy format: one header line followed by data lines with
        10 whitespace-delimited columns in this order:

            YR MON NINO12 ANOM12 NINO3 ANOM3 NINO4 ANOM4 NINO34 ANOM34

        Only the NINO12 column (index 2) is used. The local file provides
        the pre-1982 historical record not available from the NOAA online
        endpoint.

    NOAA CPC online (1982–present)
        Identical 10-column format, downloaded from:

            https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices

        The file is updated monthly; running this function always fetches
        the most recently published data.

    The two sources are concatenated and sorted by (YR, MON). Only records
    with year >= ano_inicio are taken from the local file, and only records
    with year >= 1982 are taken from the online file. This eliminates the
    overlap period and avoids potential duplicates.

    Parameters
    ----------
    local_file : str
        Path to the local SST file covering 1950–1981. Defaults to the
        project-standard location under data/input/.
    ano_inicio : int
        First year to include from the local file. Defaults to 1975 to
        match the start date of the reference Fortran program.

    Returns
    -------
    dict with keys:
        IYR  : numpy.ndarray, dtype int32   — calendar years
        MES  : numpy.ndarray, dtype int32   — months (1 = Jan … 12 = Dec)
        SST0 : numpy.ndarray, dtype float64 — NINO1+2 SST in °C

    Raises
    ------
    FileNotFoundError
        If local_file does not exist.
    RuntimeError
        If the NOAA download fails (network error, HTTP error, timeout).
    """
    # Read the local historical file (ano_inicio–1981).
    # Both the local and online files share the same 10-column format, so
    # we reuse _parse_sst_lines for both.
    with open(local_file, "r") as fh:
        local_lines = fh.readlines()
    df_local = _parse_sst_lines(local_lines, ano_inicio=ano_inicio)
    # Guard: keep only the pre-1982 record from the local file to avoid
    # double-counting the overlap if the local file extends beyond 1981.
    df_local = df_local[df_local["YR"] <= 1981]

    # Download the live NOAA record (1982–present).
    print(f"  Downloading SST from NOAA: {NOAA_SST_URL}")
    resp = _fetch(NOAA_SST_URL, "NOAA SST indices (sstoi.indices)")
    df_noaa = _parse_sst_lines(resp.text.splitlines(), ano_inicio=1982)

    # Merge, sort, and enforce correct dtypes.
    df = (
        pd.concat([df_local, df_noaa], ignore_index=True)
          .sort_values(["YR", "MON"])
          .reset_index(drop=True)
    )
    df["YR"]  = df["YR"].astype(np.int32)
    df["MON"] = df["MON"].astype(np.int32)

    print(
        f"  SST: {len(df)} months  "
        f"({df['YR'].iloc[0]}/{df['MON'].iloc[0]:02d} → "
        f"{df['YR'].iloc[-1]}/{df['MON'].iloc[-1]:02d})"
    )

    return {
        "IYR":  df["YR"].to_numpy(dtype=np.int32),
        "MES":  df["MON"].to_numpy(dtype=np.int32),
        "SST0": df["NINO12"].to_numpy(dtype=np.float64),
    }


def load_sea_level(
    station_id: str,
    station_name: str,
    start_date: str,
) -> dict:
    """
    Download hourly sea level from UHSLC ERDDAP and aggregate to monthly means.

    Background
    ----------
    UHSLC (University of Hawaii Sea Level Center) is the primary archive
    of quality-controlled, long-record tide gauge data used in sea level
    research.  Their ERDDAP service allows programmatic access to subsets
    of the archive via HTTP GET requests that return CSV.

    The FD (Fast Delivery) product provides data within days to weeks of
    collection, making it suitable for near-real-time ENSO monitoring.
    Data are reported in millimetres relative to station datum
    (station zero), which may differ between stations but is internally
    consistent within each record.

    Pipeline
    --------
    1. Download hourly observations via ERDDAP for the requested station
       and date range.
    2. Parse the ERDDAP two-row header (column names + units row skipped).
    3. Snap ±5-minute timestamp offsets to the exact clock hour.  UHSLC
       commonly delivers 04:59:59 instead of 05:00:00; without correction
       two observations land in the same resample bin, biasing the mean.
    4. Replace the UHSLC fill sentinel −32767 with NaN so missing hours
       are excluded from the monthly average rather than pulling it down
       by ~32 metres.
    5. Deduplicate on timestamp (keeping the last), drop NaN observations.
    6. Aggregate hourly → monthly via resample("MS").mean().  Monthly
       averaging matches the SST timescale and suppresses the tidal and
       weather-band signals (periods < ~1 month) irrelevant to ENSO.

    Parameters
    ----------
    station_id : str
        UHSLC numeric station identifier, zero-padded to 3 digits.
        Examples: "093" = Callao (Peru), "057" = Honolulu (Hawaii),
        "007" = Malakal/Palau (western Pacific).
    station_name : str
        Human-readable station name used only in progress messages.
    start_date : str
        ISO 8601 date string for the start of the download window.
        Pass "1905-01-01" to request the full available record; ERDDAP
        returns only what exists and ignores dates before the first obs.

    Returns
    -------
    dict with keys:
        IYR : numpy.ndarray, dtype int32   — calendar years
        MES : numpy.ndarray, dtype int32   — months (1 = Jan … 12 = Dec)
        SL0 : numpy.ndarray, dtype float64 — monthly mean sea level in mm

    Raises
    ------
    RuntimeError
        If the ERDDAP download fails or returns no usable data.
    """
    # Use UTC today as the end of the request window so we always get
    # the most recent available data without hard-coding an end year.
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    url = (
        f"{ERDDAP_BASE}"
        f"?sea_level,time"
        f"&time>={start_date}T00:00:00Z"
        f"&time<={end_date}T23:59:59Z"
        f"&uhslc_id={station_id}"
    )
    print(f"  Downloading {station_name} (UHSLC {station_id}) …")
    resp = _fetch(url, f"UHSLC ERDDAP station {station_id} ({station_name})")

    # ERDDAP prepends two header rows: column names then a units row.
    # skiprows=[1] drops the units row while keeping the column-name row.
    df = pd.read_csv(StringIO(resp.text), skiprows=[1])
    # Strip units suffixes like "sea_level (m)" → "sea_level".
    df.columns = [c.split("(")[0].strip().lower() for c in df.columns]

    if "time" not in df.columns or "sea_level" not in df.columns:
        raise RuntimeError(
            f"Unexpected ERDDAP columns for station {station_id}: "
            f"{list(df.columns)}"
        )

    # Parse timestamps as UTC-aware; clean sea level values.
    df["time_utc"] = pd.to_datetime(df["time"], utc=True)
    df["sl_mm"]    = _clean_obs(df["sea_level"])

    # Correct near-hour timestamps before deduplication so that two
    # readings at e.g. 04:59:59 and 05:00:01 collapse to one at 05:00:00.
    df["time_utc"] = _snap_to_hour(df["time_utc"])

    # Drop missing values, deduplicate, and sort.
    df = (
        df[["time_utc", "sl_mm"]]
          .dropna(subset=["sl_mm"])
          .sort_values("time_utc")
          .drop_duplicates(subset=["time_utc"], keep="last")
          .reset_index(drop=True)
    )

    if df.empty:
        raise RuntimeError(
            f"No valid observations for station {station_id} ({station_name}). "
            f"Check the station ID and date range."
        )

    print(
        f"  {station_name}: {len(df):,} hourly obs  "
        f"({df['time_utc'].iloc[0]} → {df['time_utc'].iloc[-1]})"
    )

    # Aggregate hourly → monthly mean.
    # resample("MS") = month-start frequency; .mean() automatically skips NaN.
    # dropna() removes months with zero valid observations (e.g. instrument gaps).
    df = df.set_index("time_utc")
    monthly = (
        df["sl_mm"]
          .resample("MS")
          .mean()
          .dropna()
          .reset_index()
    )
    monthly["YR"]  = monthly["time_utc"].dt.year.astype(np.int32)
    monthly["MON"] = monthly["time_utc"].dt.month.astype(np.int32)

    print(
        f"  {station_name}: {len(monthly)} monthly means  "
        f"({monthly['YR'].iloc[0]}/{monthly['MON'].iloc[0]:02d} → "
        f"{monthly['YR'].iloc[-1]}/{monthly['MON'].iloc[-1]:02d})"
    )

    return {
        "IYR": monthly["YR"].to_numpy(dtype=np.int32),
        "MES": monthly["MON"].to_numpy(dtype=np.int32),
        "SL0": monthly["sl_mm"].to_numpy(dtype=np.float64),
    }


def load_from_config(config_path: str = "config.yaml") -> dict:
    """
    Load all four datasets (SST + 3 sea level stations) using the project
    configuration file.

    This is the standard entry point for the full pipeline.  All download
    parameters (URLs, station IDs, start dates, filter constants) are kept
    in config.yaml rather than scattered across the codebase.

    Expected config.yaml structure (abridged)::

        sst:
          local_file: "data/input/sst1950_1981.txt"
          ano_inicio: 1975

        stations:
          callao:
            id: "093"
            name: "Callao"
            start_date: "1905-01-01"
          honolulu:
            id: "057"
            name: "Honolulu"
            start_date: "1905-01-01"
          palau:
            id: "007"
            name: "Palau"
            start_date: "1905-01-01"

    Parameters
    ----------
    config_path : str
        Path to the YAML configuration file.  Defaults to "config.yaml"
        in the current working directory (i.e. the project root).

    Returns
    -------
    dict with keys:
        "sst"      : dict from load_sst (IYR, MES, SST0)
        "callao"   : dict from load_sea_level (IYR, MES, SL0)
        "honolulu" : dict from load_sea_level (IYR, MES, SL0)
        "palau"    : dict from load_sea_level (IYR, MES, SL0)

    Raises
    ------
    FileNotFoundError
        If config_path does not exist.
    KeyError
        If a required configuration key is missing.
    RuntimeError
        If any download fails.
    """
    with open(config_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    sst_cfg = cfg["sst"]
    print("=== Loading SST ===")
    result = {
        "sst": load_sst(
            local_file=sst_cfg["local_file"],
            ano_inicio=sst_cfg["ano_inicio"],
        )
    }

    # Iterate over stations in config order (callao, honolulu, palau).
    # The config key becomes the output dict key so callers can do
    # data["callao"] instead of data[0].
    for key, st in cfg["stations"].items():
        print(f"\n=== Loading {st['name']} ===")
        result[key] = load_sea_level(
            station_id=st["id"],
            station_name=st["name"],
            start_date=st["start_date"],
        )

    return result


# ---------------------------------------------------------------------------
# Self-test (no network access)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Verify load_sst without making any network requests.

    Creates a small synthetic local file (3 years × 12 months = 36 rows)
    and patches _fetch to return a synthetic "online" file (2 years × 12
    months = 24 rows), then checks the merged output for correct dtypes,
    sort order, month range, and total length.
    """
    import os
    import tempfile
    from unittest.mock import MagicMock, patch

    print("Running self-test …")

    # Build synthetic file content in the 10-column NOAA format.
    # Values are arbitrary; we only verify structure, not numbers.
    header = (
        "YR  MON  NINO12  ANOM12  NINO3  ANOM3  NINO4  ANOM4  NINO34  ANOM34\n"
    )

    def _make_rows(years):
        lines = []
        for yr in years:
            for mon in range(1, 13):
                v = f"{24 + mon * 0.1:.2f}"
                lines.append(
                    f"{yr:4d} {mon:3d}  {v}  0.10"
                    f"  25.00  0.10  27.00  0.10  26.00  0.10\n"
                )
        return "".join(lines)

    # Local file covers 1979–1981; online "response" covers 1982–1983.
    local_content = header + _make_rows([1979, 1980, 1981])
    noaa_content  = header + _make_rows([1982, 1983])

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(local_content)
        tmp_path = tmp.name

    try:
        # Replace _fetch with a mock so no HTTP request is made.
        # The patch target uses __name__ so it works both when the file
        # is executed directly (__main__) and when imported as a module.
        mock_resp        = MagicMock()
        mock_resp.text   = noaa_content
        target           = f"{__name__}._fetch"

        with patch(target, return_value=mock_resp):
            data = load_sst(local_file=tmp_path, ano_inicio=1979)
    finally:
        os.unlink(tmp_path)

    IYR  = data["IYR"]
    MES  = data["MES"]
    SST0 = data["SST0"]

    # --- 1. Correct dtypes ---
    assert IYR.dtype  == np.int32,   f"FAIL: IYR dtype  = {IYR.dtype}"
    assert MES.dtype  == np.int32,   f"FAIL: MES dtype  = {MES.dtype}"
    assert SST0.dtype == np.float64, f"FAIL: SST0 dtype = {SST0.dtype}"
    print("  PASS 1: dtypes correct  (int32, int32, float64)")

    # --- 2. Years in ascending order ---
    assert np.all(np.diff(IYR) >= 0), "FAIL: years not in ascending order"
    print(f"  PASS 2: years ascending  ({IYR[0]} → {IYR[-1]})")

    # --- 3. Months all in [1, 12] ---
    assert int(MES.min()) >= 1 and int(MES.max()) <= 12, (
        f"FAIL: months out of [1, 12]  (found {MES.min()} to {MES.max()})"
    )
    print(f"  PASS 3: months in [1, 12]  (min={MES.min()}, max={MES.max()})")

    # --- 4. Expected record count: 1979–1983 = 5 years × 12 months ---
    expected = 5 * 12
    assert len(SST0) == expected, (
        f"FAIL: expected {expected} rows, got {len(SST0)}"
    )
    print(f"  PASS 4: record count correct  ({len(SST0)} months)")

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
