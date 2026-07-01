"""
el_nino.download
================
Data acquisition: SST from NOAA CPC and hourly sea level from UHSLC ERDDAP.

All public functions return plain dicts of NumPy arrays so callers have no
dependency on pandas beyond this module boundary.
"""

from __future__ import annotations

import shutil
import time
import warnings
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

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

# Retry policy for transient network failures (timeouts, dropped connections).
# UHSLC's ERDDAP/RQD servers intermittently stall; a couple of backed-off
# retries turns a hard failure into a recoverable blip. Non-transient errors
# (e.g. HTTP 404) are never retried.
RETRY_BACKOFFS = (2, 5, 10)   # seconds to wait before attempts 2, 3, 4

# RAPID near-real-time URLs tried in order; {id} tozero-padded station_id.
# URL 1: FD hourly CSV (same data as ERDDAP FD, different transport).
# URL 2: Station RAPID stream (StationZero datum, GMT).
# URL 3: ERDDAP Research Quality Data Set (RQDS) endpoint.
_RAPID_URL_TEMPLATES = [
    "https://uhslc.soest.hawaii.edu/data/csv/fast/hourly/h{id}.csv",
    "http://uhslc.soest.hawaii.edu/stations/RAPID/{id}_mm_StationZero_GMT.csv",
    (
        "https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_rqds.csv"
        "?sea_level%2Ctime&uhslc_id={id}"
    ),
]

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

    Transient failures (connection timeouts and dropped connections) are
    retried with exponential backoff per ``RETRY_BACKOFFS`` before giving up.
    UHSLC's servers stall intermittently, so a couple of backed-off retries
    turn an otherwise-fatal blip into a recoverable one. HTTP errors (e.g. a
    404) are *not* retried — they will not fix themselves — and are raised
    immediately.

    Wraps network errors in a RuntimeError with a human-readable message
    that includes the URL — useful when the failure is deep in a pipeline.
    """
    # One attempt per backoff plus the initial try (e.g. 2/5/10 → 4 attempts).
    total_attempts = len(RETRY_BACKOFFS) + 1
    for attempt in range(total_attempts):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            # Transient: retry with backoff unless this was the last attempt.
            if attempt < len(RETRY_BACKOFFS):
                wait = RETRY_BACKOFFS[attempt]
                warnings.warn(
                    f"Transient network error downloading {label} "
                    f"(attempt {attempt + 1}/{total_attempts}): {exc}. "
                    f"Retrying in {wait}s …",
                    stacklevel=2,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"Network error downloading {label} after "
                f"{total_attempts} attempts: {exc}\n"
                f"URL: {url}"
            ) from exc
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


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column present in df that matches any candidate name."""
    for cand in candidates:
        if cand in df.columns:
            return cand
    return None


def _save_raw(path: str, content: str) -> None:
    """Write ``content`` to ``path``; silently warns on failure."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as exc:
        warnings.warn(f"Could not save {path}: {exc}")


def _parse_rapid_csv(text: str) -> pd.DataFrame | None:
    """
    Try multiple CSV parse strategies and return a normalised DataFrame.

    Handles three source formats:
    1. ERDDAP format: column names row + units row (skiprows=[1]).
    2. Simple CSV with a single time column and a sea level column.
    3. Year/Month/Day/Hour component columns (construct datetime).

    Returns a DataFrame with columns ``time_utc`` and ``sl_mm``, or None
    if no strategy produces usable data.
    """
    # ── Strategy 1: ERDDAP two-row header (column names + units) ─────────────
    try:
        df = pd.read_csv(StringIO(text), skiprows=[1])
        df.columns = [c.split("(")[0].strip().lower() for c in df.columns]
        t_col  = _find_col(df, ["time", "time_utc"])
        sl_col = _find_col(df, ["sea_level", "obs", "observation", "sl_mm", "sl"])
        if t_col and sl_col:
            df["time_utc"] = pd.to_datetime(df[t_col], utc=True, errors="coerce")
            df["sl_mm"]    = _clean_obs(df[sl_col])
            out = df[["time_utc", "sl_mm"]].dropna()
            if not out.empty:
                return out.reset_index(drop=True)
    except Exception:
        pass

    # ── Strategy 2: Plain CSV with a single datetime/time column ─────────────
    try:
        df = pd.read_csv(StringIO(text))
        df.columns = [c.split("(")[0].strip().lower() for c in df.columns]
        t_col  = _find_col(df, ["time", "time_utc", "datetime", "date_time",
                                 "date", "timestamp"])
        sl_col = _find_col(df, ["sea_level", "obs", "observation", "sl_mm",
                                 "sl", "water_level", "level"])
        if t_col and sl_col:
            df["time_utc"] = pd.to_datetime(df[t_col], utc=True, errors="coerce")
            df["sl_mm"]    = _clean_obs(df[sl_col])
            out = df[["time_utc", "sl_mm"]].dropna()
            if not out.empty:
                return out.reset_index(drop=True)
    except Exception:
        pass

    # ── Strategy 3: Year/Month/Day/Hour component columns ────────────────────
    try:
        df = pd.read_csv(StringIO(text))
        df.columns = [c.strip().lower() for c in df.columns]
        yr_col = _find_col(df, ["year", "yr"])
        mo_col = _find_col(df, ["month", "mon"])
        dy_col = _find_col(df, ["day"])
        hr_col = _find_col(df, ["hour", "hr"])
        sl_col = _find_col(df, ["sea_level", "obs", "observation", "sl_mm",
                                 "sl", "water_level"])
        if yr_col and mo_col and dy_col and hr_col and sl_col:
            df["time_utc"] = pd.to_datetime(
                {
                    "year":  pd.to_numeric(df[yr_col],  errors="coerce"),
                    "month": pd.to_numeric(df[mo_col], errors="coerce"),
                    "day":   pd.to_numeric(df[dy_col],   errors="coerce"),
                    "hour":  pd.to_numeric(df[hr_col],  errors="coerce"),
                },
                utc=True,
                errors="coerce",
            )
            df["sl_mm"] = _clean_obs(df[sl_col])
            out = df[["time_utc", "sl_mm"]].dropna()
            if not out.empty:
                return out.reset_index(drop=True)
    except Exception:
        pass

    return None


def _load_rapid(station_id: str) -> pd.DataFrame:
    """
    Attempt to download near-real-time sea level from UHSLC RAPID sources.

    Tries each URL in ``_RAPID_URL_TEMPLATES`` in order, stopping at the
    first that returns usable data.  All failures are silently swallowed so
    that a RAPID outage never aborts the main pipeline; the caller checks
    whether the returned DataFrame is empty.

    Parameters
    ----------
    station_id : str
        Zero-padded UHSLC station ID (e.g. "093").

    Returns
    -------
    pd.DataFrame
        Columns: ``time_utc`` (UTC-aware datetime), ``sl_mm`` (float).
        Empty DataFrame if all URLs fail.
    """
    _empty = pd.DataFrame(columns=["time_utc", "sl_mm"])

    for template in _RAPID_URL_TEMPLATES:
        url = template.format(id=station_id)
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            if not resp.text.strip():
                continue

            df = _parse_rapid_csv(resp.text)
            if df is None or df.empty:
                continue

            # Apply the same ±5-minute snap used for FD data.
            df["time_utc"] = _snap_to_hour(df["time_utc"])
            df = (
                df.dropna(subset=["sl_mm"])
                  .sort_values("time_utc")
                  .drop_duplicates(subset=["time_utc"], keep="last")
                  .reset_index(drop=True)
            )
            if df.empty:
                continue

            _save_raw(f"data/input/rapid_{station_id}_raw.csv", resp.text)
            print(
                f"  RAPID: {len(df):,} records  "
                f"({df['time_utc'].iloc[0]} to{df['time_utc'].iloc[-1]})"
            )
            return df

        except Exception:
            continue

    print(f"  RAPID: all URLs failed, using FD only")
    return _empty


def _merge_fd_rapid(
    df_fd: pd.DataFrame,
    df_rapid: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine Fast Delivery and RAPID DataFrames, RAPID taking priority.

    When the two sources overlap in time (same ``time_utc``), the RAPID
    observation is kept and the FD observation is discarded.  This is done
    by assigning a numeric priority (FD=1, RAPID=2), sorting by
    (time_utc, priority), then keeping the last entry per timestamp.

    Parameters
    ----------
    df_fd    : pd.DataFrame — columns time_utc, sl_mm  (Fast Delivery)
    df_rapid : pd.DataFrame — columns time_utc, sl_mm  (RAPID)

    Returns
    -------
    pd.DataFrame
        Merged and deduplicated DataFrame with columns time_utc, sl_mm,
        sorted by time_utc ascending.
    """
    if df_rapid.empty:
        return df_fd.reset_index(drop=True)
    if df_fd.empty:
        return df_rapid.reset_index(drop=True)

    fd_p    = df_fd.copy();    fd_p["_pri"]    = 1
    rapid_p = df_rapid.copy(); rapid_p["_pri"] = 2

    merged = (
        pd.concat([fd_p, rapid_p], ignore_index=True)
          .sort_values(["time_utc", "_pri"])
          .drop_duplicates(subset=["time_utc"], keep="last")
          .drop(columns=["_pri"])
          .sort_values("time_utc")
          .reset_index(drop=True)
    )
    return merged[["time_utc", "sl_mm"]]


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
    # File 2: preserve the historical source file as-is.
    _save_raw("data/input/sst_historical_pre1982.txt", "".join(local_lines))
    df_local = _parse_sst_lines(local_lines, ano_inicio=ano_inicio)
    # Guard: keep only the pre-1982 record from the local file to avoid
    # double-counting the overlap if the local file extends beyond 1981.
    df_local = df_local[df_local["YR"] <= 1981]

    # Download the live NOAA record (1982–present).
    print(f"  Downloading SST from NOAA: {NOAA_SST_URL}")
    resp = _fetch(NOAA_SST_URL, "NOAA SST indices (sstoi.indices)")
    # File 1: save the exact NOAA response text.
    _save_raw("data/input/noaa_sstoi_raw.txt", resp.text)
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
        f"({df['YR'].iloc[0]}/{df['MON'].iloc[0]:02d} to"
        f"{df['YR'].iloc[-1]}/{df['MON'].iloc[-1]:02d})"
    )

    # File 3: combined SST series (NINO1+2 only, legacy format).
    _ym = datetime.now(timezone.utc).strftime("%Y-%m")
    _sst_lines = [
        f"# SST combined series (NINO1+2) generated {_ym}\n",
        "year  month  sst_degC\n",
    ]
    for _r in df.itertuples(index=False):
        _sst_lines.append(f"{_r.YR:4d}  {_r.MON:5d}  {_r.NINO12:.4f}\n")
    _save_raw(f"data/input/sst_combined_{_ym}.txt", "".join(_sst_lines))

    # File 3b: all four index columns for downstream use.
    _idx_lines = [
        f"# SST combined all indices generated {_ym}\n",
        "year month nino12 anom12 nino3 anom3 nino4 anom4 nino34 anom34\n",
    ]
    for _r in df.itertuples(index=False):
        _idx_lines.append(
            f"{_r.YR:4d} {_r.MON:3d}"
            f"  {_r.NINO12:.4f}  {_r.ANOM12:.4f}"
            f"  {_r.NINO3:.4f}  {_r.ANOM3:.4f}"
            f"  {_r.NINO4:.4f}  {_r.ANOM4:.4f}"
            f"  {_r.NINO34:.4f}  {_r.ANOM34:.4f}\n"
        )
    _save_raw(f"data/input/sst_combined_indices_{_ym}.txt", "".join(_idx_lines))

    return {
        "IYR":   df["YR"].to_numpy(dtype=np.int32),
        "MES":   df["MON"].to_numpy(dtype=np.int32),
        "SST0":  df["NINO12"].to_numpy(dtype=np.float64),
        "ANOM12": df["ANOM12"].to_numpy(dtype=np.float64),
        "SST3":  df["NINO3"].to_numpy(dtype=np.float64),
        "ANOM3": df["ANOM3"].to_numpy(dtype=np.float64),
        "SST4":  df["NINO4"].to_numpy(dtype=np.float64),
        "ANOM4": df["ANOM4"].to_numpy(dtype=np.float64),
        "SST34": df["NINO34"].to_numpy(dtype=np.float64),
        "ANOM34": df["ANOM34"].to_numpy(dtype=np.float64),
    }


def _load_sea_level_erddap(
    station_id: str,
    station_name: str,
    start_date: str,
) -> dict:
    """Download + aggregate via UHSLC ERDDAP FD + RAPID. Raises RuntimeError on failure."""
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
    _save_raw(f"data/input/uhslc_fd_{station_id}_raw.csv", resp.text)

    df = pd.read_csv(StringIO(resp.text), skiprows=[1])
    df.columns = [c.split("(")[0].strip().lower() for c in df.columns]

    if "time" not in df.columns or "sea_level" not in df.columns:
        raise RuntimeError(
            f"Unexpected ERDDAP columns for station {station_id}: "
            f"{list(df.columns)}"
        )

    df["time_utc"] = pd.to_datetime(df["time"], utc=True)
    df["sl_mm"]    = _clean_obs(df["sea_level"])
    df["time_utc"] = _snap_to_hour(df["time_utc"])
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
        f"({df['time_utc'].iloc[0]} to{df['time_utc'].iloc[-1]})"
    )

    df_rapid = _load_rapid(station_id)
    if not df_rapid.empty:
        fd_last    = df["time_utc"].max()
        rapid_tail = df_rapid[df_rapid["time_utc"] > fd_last].copy()
        if not rapid_tail.empty:
            n_ext = len(rapid_tail)
            df = _merge_fd_rapid(df, rapid_tail)
            print(f"  Extended record with RAPID: {n_ext:,} additional hours")

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
        f"({monthly['YR'].iloc[0]}/{monthly['MON'].iloc[0]:02d} to"
        f"{monthly['YR'].iloc[-1]}/{monthly['MON'].iloc[-1]:02d})"
    )

    _ym = datetime.now(timezone.utc).strftime("%Y-%m")
    _sl_lines = [
        f"# SSH combined monthly means station {station_id} generated {_ym}\n",
        "year  month  sea_level_mm\n",
    ]
    for _r in monthly.itertuples(index=False):
        _sl_lines.append(f"{_r.YR:4d}  {_r.MON:5d}  {_r.sl_mm:.2f}\n")
    _save_raw(
        f"data/input/ssh_combined_{station_id}_{_ym}.txt",
        "".join(_sl_lines),
    )

    return {
        "IYR": monthly["YR"].to_numpy(dtype=np.int32),
        "MES": monthly["MON"].to_numpy(dtype=np.int32),
        "SL0": monthly["sl_mm"].to_numpy(dtype=np.float64),
    }


def load_sea_level_rqd(url: str, station_name: str) -> dict:
    """
    Download UHSLC Research Quality Data (RQD) hourly CSV and aggregate to monthly means.

    The RQD CSV format is whitespace-separated with five columns:
        year  month  day  hour  sea_level_mm
    Missing values are encoded as -32767 or -32768.

    Parameters
    ----------
    url          : str — direct URL to the RQD hourly CSV file
    station_name : str — human-readable station name (for progress messages)

    Returns
    -------
    dict with keys IYR (int32), MES (int32), SL0 (float64)

    Raises
    ------
    RuntimeError
        If the download fails or produces no usable data.
    """
    print(f"  [{station_name}] Trying RQD fallback: {url}")
    resp = _fetch(url, f"UHSLC RQD {station_name}")

    # Derive station id from URL for saving raw file.
    _sid = url.rstrip("/").split("/")[-1].split(".")[0].lstrip("h")
    _save_raw(f"data/input/rqd_{_sid}_raw.csv", resp.text)

    # Parse: whitespace-separated, 5 columns, no header.
    rows = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            yr, mo, dy, hr = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            sl = float(parts[4])
        except ValueError:
            continue
        if sl in (-32767, -32768) or np.isnan(sl):
            continue
        rows.append((yr, mo, dy, hr, sl))

    if not rows:
        raise RuntimeError(f"RQD file for {station_name} contains no valid data.")

    import pandas as pd
    df = pd.DataFrame(rows, columns=["year", "month", "day", "hour", "sl_mm"])
    df["time_utc"] = pd.to_datetime(
        {"year": df["year"], "month": df["month"], "day": df["day"], "hour": df["hour"]},
        utc=True, errors="coerce",
    )
    df = df.dropna(subset=["time_utc"]).set_index("time_utc")

    # 50 % valid-hour threshold per month.
    monthly_count = df["sl_mm"].resample("MS").count()
    monthly_mean  = df["sl_mm"].resample("MS").mean()
    days_in_month = monthly_mean.index.days_in_month
    monthly_mean  = monthly_mean[monthly_count >= days_in_month * 24 * 0.5]
    monthly_mean  = monthly_mean.dropna().reset_index()

    if monthly_mean.empty:
        raise RuntimeError(f"RQD data for {station_name}: no months passed 50% valid threshold.")

    monthly_mean["YR"]  = monthly_mean["time_utc"].dt.year.astype(np.int32)
    monthly_mean["MON"] = monthly_mean["time_utc"].dt.month.astype(np.int32)

    print(
        f"  {station_name} (RQD): {len(monthly_mean)} monthly means  "
        f"({monthly_mean['YR'].iloc[0]}/{monthly_mean['MON'].iloc[0]:02d} to"
        f"{monthly_mean['YR'].iloc[-1]}/{monthly_mean['MON'].iloc[-1]:02d})"
    )
    return {
        "IYR": monthly_mean["YR"].to_numpy(dtype=np.int32),
        "MES": monthly_mean["MON"].to_numpy(dtype=np.int32),
        "SL0": monthly_mean["sl_mm"].to_numpy(dtype=np.float64),
    }


def load_sea_level(
    station_id: str,
    station_name: str,
    start_date: str,
    rqd_url: str | None = None,
) -> dict:
    """
    Download hourly sea level from UHSLC ERDDAP, extend with RAPID
    near-real-time data, and aggregate to monthly means.

    Background
    ----------
    UHSLC (University of Hawaii Sea Level Center) is the primary archive
    of quality-controlled, long-record tide gauge data used in sea level
    research.  Their ERDDAP service allows programmatic access to subsets
    of the archive via HTTP GET requests that return CSV.

    The FD (Fast Delivery) product provides data within days to weeks of
    collection, making it suitable for near-real-time ENSO monitoring.
    RAPID sources extend the record to within hours of the present,
    but without the QC applied to the FD archive; they are therefore
    appended only after the last FD timestamp to preserve archive integrity.

    Pipeline
    --------
    1. Download hourly observations via ERDDAP FD for the requested station
       and date range.
    2. Parse the ERDDAP two-row header (column names + units row skipped).
    3. Snap ±5-minute timestamp offsets to the exact clock hour.
    4. Replace the UHSLC fill sentinel −32767 with NaN.
    5. Deduplicate on timestamp (keeping the last), drop NaN observations.
    6. Attempt RAPID extension: try three near-real-time URLs in order;
       append only observations strictly after the last FD timestamp.
    7. Aggregate hourly tomonthly via resample("MS").mean().

    Parameters
    ----------
    station_id : str
        UHSLC numeric station identifier, zero-padded to 3 digits.
    station_name : str
        Human-readable station name used only in progress messages.
    start_date : str
        ISO 8601 date string for the start of the download window.

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
    try:
        return _load_sea_level_erddap(station_id, station_name, start_date)
    except RuntimeError as erddap_exc:
        if rqd_url is None:
            raise
        warnings.warn(
            f"ERDDAP failed for {station_name} ({erddap_exc}); "
            f"falling back to RQD.",
            stacklevel=2,
        )
        try:
            return load_sea_level_rqd(rqd_url, station_name)
        except RuntimeError as rqd_exc:
            raise RuntimeError(
                f"Both ERDDAP and RQD failed for {station_name}.\n"
                f"  ERDDAP: {erddap_exc}\n"
                f"  RQD:    {rqd_exc}"
            ) from rqd_exc


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
        "sst"         : dict from load_sst (IYR, MES, SST0, ANOM12, …)
        "<station_key>": dict from load_sea_level (IYR, MES, SL0) for each
                         station defined in config.yaml

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

    for key, st in cfg["stations"].items():
        print(f"\n=== Loading {st['name']} ===")
        result[key] = load_sea_level(
            station_id=st["id"],
            station_name=st["name"],
            start_date=st["start_date"],
            rqd_url=st.get("rqd_url"),
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
    print(f"  PASS 2: years ascending  ({IYR[0]} to{IYR[-1]})")

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
