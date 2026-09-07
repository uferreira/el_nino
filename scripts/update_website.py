"""
scripts/update_website.py
=========================
Download fresh ENSO data, run the Python Fourier pipeline (which writes the
reference ``data/output/*.dat`` files), and re-embed the **raw monthly
input series** in every docs/*.html page.

Run from the project root:

    python scripts/update_website.py              # all datasets
    python scripts/update_website.py --sst-only   # only the SST indices
    python scripts/update_website.py --dry-run    # compute but do not write
    python scripts/update_website.py --no-push    # update HTML but skip git push
    python scripts/update_website.py --allow-older  # let data move backwards

Published data only moves forwards
----------------------------------
Before writing anything the script compares each dataset's fresh last month
against the one the page already publishes, and aborts if any would move
backwards. That is the signature of an unreachable source or a stale
``data/input/`` cache: the pipeline still succeeds, but on a shorter record,
and writing it would quietly un-publish real observations. ``--allow-older``
overrides the check when the older record is genuinely the correct one.

What the pages contain
----------------------
Between the ``// ENSO_DATA_BEGIN`` and ``// ENSO_DATA_END`` markers each page
carries a ``RAW_SERIES`` object of unfiltered monthly observations, followed
by the lines that turn it into the filtered/interpolated arrays the plots
read.  The filtering itself happens **in the browser**, in
``docs/assets/js/fourier-filter.js``, so a visitor can change the Fourier
analysis window (the date selector rendered by
``docs/assets/js/fourier-window.js``) and have everything recomputed without
a new pipeline run.

The Python pipeline remains the reference implementation: it runs the same
maths over the window configured in ``config.yaml`` (``filter.window``) and
writes the ``.dat`` files.  ``tests/test_fourier_window_parity.py`` asserts
the two agree.

Dataset -> JS name mapping
--------------------------
    sva.2_filter_NINO12_SAIDApy.dat      -> observedData  / OBS_N
    sva.2_filter_NINO3_SAIDApy.dat       -> nino3Data     / NINO3_N
    sva.2_filter_NINO4_SAIDApy.dat       -> nino4Data     / NINO4_N
    sva.2_filter_NINO34_SAIDApy.dat      -> nino34Data    / NINO34_N
    sva.2_filter_Callao_SAIDApy.dat      -> callaoData    / CAL_N
    sva.2_filter_La Libertad_SAIDApy.dat -> laLibData     / LALIB_N
    sva.2_filter_Honolulu_SAIDApy.dat    -> honoluluData  / HON_N
    sva.2_filter_Palau_SAIDApy.dat       -> palauData     / PAL_N
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # must be before any pyplot import

import yaml

from el_nino import pipeline


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONTH_NAMES = [
    "Jan","Feb","Mar","Apr","May","Jun",
    "Jul","Aug","Sep","Oct","Nov","Dec",
]

MONTH_FULL = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
]

OUT_DIR = Path("data/output")
CONFIG  = Path("config.yaml")
DOCS    = Path("docs")

# Per-station data-freshness tracking, persisted across runs so a station
# that fails one run still remembers when it was last successfully refreshed.
# Lives under data/output/ (gitignored) but is force-committed by the update
# workflow so it survives the ephemeral CI checkout.
FRESHNESS_FILE = OUT_DIR / "freshness.json"

# All known datasets, in the order they are written into RAW_SERIES.
#   js_var -> (dat_filename, length_constant, label, unit, group, deseasonalize)
# "deseasonalize" mirrors the Python pipeline: absolute series have their
# monthly climatology removed before the filter and added back afterwards;
# the NOAA NINO3/4/3.4 columns are already anomalies and are filtered as-is.
DATASETS: OrderedDict[str, dict] = OrderedDict([
    ("observedData", dict(dat="sva.2_filter_NINO12_SAIDApy.dat",      len="OBS_N",
                          label="NINO1+2 SST",    unit="\u00b0C", group="sst", deseasonalize=True)),
    ("nino3Data",    dict(dat="sva.2_filter_NINO3_SAIDApy.dat",       len="NINO3_N",
                          label="NINO3 anomaly",  unit="\u00b0C", group="sst", deseasonalize=False)),
    ("nino4Data",    dict(dat="sva.2_filter_NINO4_SAIDApy.dat",       len="NINO4_N",
                          label="NINO4 anomaly",  unit="\u00b0C", group="sst", deseasonalize=False)),
    ("nino34Data",   dict(dat="sva.2_filter_NINO34_SAIDApy.dat",      len="NINO34_N",
                          label="NINO3.4 anomaly", unit="\u00b0C", group="sst", deseasonalize=False)),
    ("callaoData",   dict(dat="sva.2_filter_Callao_SAIDApy.dat",      len="CAL_N",
                          label="Callao SL",      unit="mm", group="sl", deseasonalize=True)),
    ("laLibData",    dict(dat="sva.2_filter_La Libertad_SAIDApy.dat", len="LALIB_N",
                          label="La Libertad SL", unit="mm", group="sl", deseasonalize=True)),
    ("honoluluData", dict(dat="sva.2_filter_Honolulu_SAIDApy.dat",    len="HON_N",
                          label="Honolulu SL",    unit="mm", group="sl", deseasonalize=True)),
    ("palauData",    dict(dat="sva.2_filter_Palau_SAIDApy.dat",       len="PAL_N",
                          label="Palau SL",       unit="mm", group="sl", deseasonalize=True)),
])

DATA_BEGIN = "// ENSO_DATA_BEGIN"
DATA_END   = "// ENSO_DATA_END"

# All HTML pages to patch (skipped silently if not found)
HTML_FILES = [
    DOCS / "index.html",
    DOCS / "phase_diagrams.html",
    DOCS / "duffing_simulation.html",
    DOCS / "familiar_attractor.html",
    DOCS / "ensemble.html",
    DOCS / "compare.html",
]

# A Fast Delivery tide gauge normally reaches the current or immediately
# preceding month. Allow a two-month grace period for temporary telemetry
# and publication delays; older endpoints are visibly marked as stale even
# when the download itself succeeds.
STALE_AFTER_MONTHS = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month-1]} {year}"


def _pts_label(n: int) -> str:
    return f"{n:,}"


def _compact_array(values, fmt: str) -> str:
    """Render a list of numbers as a compact JS array literal."""
    return "[" + ",".join(format(v, fmt) for v in values) + "]"


def _load_dat(path: str) -> dict:
    """Parse a pipeline .dat file into lists (not NumPy, for JS serialisation)."""
    xs, ys, years, months, irests = [], [], [], [], []
    with open(path) as fh:
        for line in fh:
            parts = line.strip().split(";")
            if len(parts) < 5:
                continue
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
            years.append(int(parts[2]))
            months.append(int(parts[3]))
            irests.append(int(parts[4]))
    return {"x": xs, "y": ys, "year": years, "month": months, "irest": irests}


def _as_raw(raw_full: dict) -> dict:
    """Pipeline ``raw_full`` (NumPy) -> plain lists for JS serialisation.

    These are the unfiltered monthly observations over the dataset's whole
    record, not the analysis window: the browser needs the full record so a
    visitor can widen the window as well as narrow it.
    """
    return {
        "values": [float(v) for v in raw_full["values"]],
        "year":   [int(v)   for v in raw_full["IYR"]],
        "month":  [int(v)   for v in raw_full["MES"]],
    }


def _js_str(text: str) -> str:
    """Minimal JS string literal (the values here are ASCII labels/units)."""
    return json.dumps(text, ensure_ascii=False)


def _build_raw_entry(var_name: str, meta: dict, raw: dict) -> str:
    """One RAW_SERIES member: the unfiltered monthly observations."""
    return (
        f"  {var_name}: {{label:{_js_str(meta['label'])},unit:{_js_str(meta['unit'])},"
        f"group:{_js_str(meta['group'])},deseasonalize:{'true' if meta['deseasonalize'] else 'false'},\n"
        f"    values:{_compact_array(raw['values'], '.2f')},\n"
        f"    year:{_compact_array(raw['year'], 'd')},\n"
        f"    month:{_compact_array(raw['month'], 'd')}}}"
    )


def _last_month(raw: dict) -> tuple[int, int] | None:
    """Last (year, month) of a raw series, in either shape it comes in.

    Accepts the pipeline shape (``IYR``/``MES``) and the page shape
    (``year``/``month``), so a freshly computed series and one parsed back
    out of a published page can be compared directly.
    """
    years = raw.get("year") or raw.get("IYR")
    months = raw.get("month") or raw.get("MES")
    if not years or not months:
        return None
    return int(years[-1]), int(months[-1])


def _check_no_regression(
    html_name: str,
    computed: dict[str, dict],
    published: "OrderedDict[str, dict]",
) -> list[str]:
    """Report datasets whose fresh series ends EARLIER than the published one.

    Data must only ever move forwards. A run that produces an older record
    means the sources were incomplete, or the pipeline fell back to a stale
    local cache — not that a month disappeared from the ocean. Overwriting
    the page in that case silently un-publishes real observations, which is
    exactly the failure this guard exists to catch.
    """
    losses: list[str] = []
    for var_name, raw in computed.items():
        prev = published.get(var_name)
        if prev is None:
            continue
        new_last, old_last = _last_month(raw), _last_month(prev)
        if new_last is None or old_last is None:
            continue
        if new_last < old_last:
            losses.append(
                f"{html_name}: {var_name} would move back from "
                f"{_month_label(*old_last)} to {_month_label(*new_last)}"
            )
    return losses


def _build_data_region(raw_series: "OrderedDict[str, dict]",
                       hn1: float, hn2: float, ndots: int,
                       base_year: int) -> str:
    """Build the whole generated block, markers included.

    The block embeds the RAW monthly observations and then hands them to
    EnsoFourier (docs/assets/js/fourier-filter.js), which reproduces the
    Python pipeline in the browser. Nothing pre-filtered is shipped, so the
    date selector can re-run the analysis over any window the visitor picks.
    """
    entries = ",\n".join(
        _build_raw_entry(var_name, DATASETS[var_name], raw)
        for var_name, raw in raw_series.items()
    )
    derived = "\n".join(
        f"const {var_name} = FOURIER_RESULTS.{var_name};\n"
        f"const {DATASETS[var_name]['len']} = {var_name}.x.length;"
        for var_name in raw_series
    )
    return f"""{DATA_BEGIN}
/* Generated by scripts/update_website.py — do not edit by hand.

   RAW_SERIES holds the UNFILTERED monthly observations. The Fourier
   low-pass filter, the interpolation onto {ndots} sub-points per month and the
   derivatives all run in the browser, in assets/js/fourier-filter.js, so
   the analysis window can be changed from the date selector at the top of
   the page. The Python reference implementation of the same maths is
   src/el_nino/filter.py + src/el_nino/pipeline.py, and it is what writes
   the data/output/*.dat files.                                          */
const RAW_SERIES = {{
{entries}
}};
/* Filter parameters — config.yaml: filter (HN1, HN2, NDOTS, window.base_year) */
const FOURIER_PARAMS = {{HN1:{hn1}, HN2:{hn2}, NDOTS:{ndots}, baseYear:{base_year}}};
/* Requested window: ?from=YYYY-MM&to=YYYY-MM, else this session's choice,
   else the default (base year, month after the end month, so the record
   spans whole 12-month cycles). */
const FOURIER_REQUEST = EnsoFourierWindow.request();
const FOURIER_RESULTS = EnsoFourier.runAll(RAW_SERIES, FOURIER_PARAMS, FOURIER_REQUEST);
{derived}
document.addEventListener('DOMContentLoaded', function () {{
  EnsoFourierWindow.mount({{
    rawSeries: RAW_SERIES, params: FOURIER_PARAMS, results: FOURIER_RESULTS,
    plotSeries: window.FOURIER_PLOT_SERIES || {{}}
  }});
}});
{DATA_END}"""


# Legacy layout: a run of `const <var> = {{...}}; const <LEN> = ...` blocks,
# from the first dataset to the last. Matched once so the first run of this
# script migrates a page to the marker-delimited region above.
_LEGACY_REGION = re.compile(
    # Greedy on purpose: the run of blocks must be consumed to its very last
    # length constant, whatever order the page listed the datasets in.
    r"const observedData\s*=\s*\{.*"
    r"const (?:OBS_N|NINO3_N|NINO4_N|NINO34_N|CAL_N|TAL_N|LALIB_N|HON_N|PAL_N)"
    r"\s*=\s*\w+\.x\.length;[^\n]*",
    re.DOTALL,
)

_MARKED_REGION = re.compile(
    re.escape(DATA_BEGIN) + r".*?" + re.escape(DATA_END), re.DOTALL
)


def _patch_data_region(html: str, region: str) -> tuple[str, bool]:
    """Replace the generated data region, migrating a legacy page if needed."""
    if DATA_BEGIN in html:
        return _MARKED_REGION.sub(lambda _m: region, html, count=1), True
    new_html, count = _LEGACY_REGION.subn(lambda _m: region, html, count=1)
    return new_html, count > 0


def _extract_raw_series(html: str) -> "OrderedDict[str, dict]":
    """Read RAW_SERIES back out of a page.

    Needed by --sst-only / --sl-only: the region is rewritten as a whole, so
    the datasets that were not re-run this time must keep the values already
    published rather than disappearing from the page.
    """
    found: "OrderedDict[str, dict]" = OrderedDict()
    for var_name in DATASETS:
        m = re.search(
            rf"{re.escape(var_name)}:\s*\{{[^{{}}]*?values:\[([^\]]*)\],\s*"
            rf"year:\[([^\]]*)\],\s*month:\[([^\]]*)\]\}}",
            html, re.DOTALL,
        )
        if not m:
            continue
        found[var_name] = {
            "values": [float(v) for v in m.group(1).split(",") if v.strip()],
            "year":   [int(v)   for v in m.group(2).split(",") if v.strip()],
            "month":  [int(v)   for v in m.group(3).split(",") if v.strip()],
        }
    return found


def _patch_stats_bar(html: str,
                     sst_yr0: int, sst_m0: int, sst_yr1: int, sst_m1: int,
                     sst_n: int,
                     cal_yr0: int, cal_m0: int, cal_yr1: int, cal_m1: int,
                     cal_n: int) -> str:
    """Update the human-readable date-range and point-count spans in index.html."""
    obs_range = f"{_month_label(sst_yr0, sst_m0)} – {_month_label(sst_yr1, sst_m1)}"
    cal_range = f"{_month_label(cal_yr0, cal_m0)} – {_month_label(cal_yr1, cal_m1)}"
    obs_pts   = _pts_label(sst_n)
    cal_pts   = _pts_label(cal_n)

    # First Period/Points occurrences → SST section
    html = re.sub(
        r"(Period:\s*<strong>)([^<]+)(</strong>)",
        lambda m: m.group(1) + obs_range + m.group(3),
        html, count=1,
    )
    html = re.sub(
        r"(Points:\s*<strong>)([\d,]+)(</strong>)",
        lambda m: m.group(1) + obs_pts + m.group(3),
        html, count=1,
    )
    # Second Period/Points occurrences → Callao section
    html = re.sub(
        r"(Period:\s*<strong>)([^<]+)(</strong>)",
        lambda m: m.group(1) + cal_range + m.group(3),
        html, count=1,
    )
    html = re.sub(
        r"(Points:\s*<strong>)([\d,]+)(</strong>)",
        lambda m: m.group(1) + cal_pts + m.group(3),
        html, count=1,
    )
    # Header subtitle year ranges
    html = re.sub(
        r"(NINO1\+2 SST )(\d{4}–\d{4})",
        lambda m: m.group(1) + f"{sst_yr0}–{sst_yr1}",
        html,
    )
    html = re.sub(
        r"(Callao SL )(\d{4}–\d{4})",
        lambda m: m.group(1) + f"{cal_yr0}–{cal_yr1}",
        html,
    )
    return html


def _count_monthly(dat_file: Path) -> int:
    """Count irest==0 lines (original monthly points) in a .dat file."""
    n = 0
    with open(dat_file) as fh:
        for line in fh:
            parts = line.strip().split(";")
            if len(parts) >= 5 and int(parts[4]) == 0:
                n += 1
    return n


# ---------------------------------------------------------------------------
# Data-freshness tracking
# ---------------------------------------------------------------------------

def _load_freshness() -> dict:
    """Load the persisted freshness state, or an empty skeleton if absent/corrupt."""
    try:
        state = json.loads(FRESHNESS_FILE.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            state.setdefault("stations", {})
            return state
    except (FileNotFoundError, ValueError, OSError):
        pass
    return {"last_refreshed": None, "stations": {}}


def _save_freshness(state: dict) -> None:
    """Persist the freshness state as pretty JSON (best-effort)."""
    try:
        FRESHNESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FRESHNESS_FILE.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"  WARNING: could not write {FRESHNESS_FILE}: {exc}", file=sys.stderr)


def _fmt_run_date(dt: datetime) -> str:
    """Format a UTC datetime as e.g. '1 July 2026'."""
    return f"{dt.day} {MONTH_FULL[dt.month - 1]} {dt.year}"


def _fmt_month(ym: str | None) -> str | None:
    """Format a 'YYYY-MM' string as e.g. 'June 2026'; None if unparseable."""
    if not ym:
        return None
    try:
        y, m = ym.split("-")
        return f"{MONTH_FULL[int(m) - 1]} {int(y)}"
    except (ValueError, IndexError):
        return None


def _stale_notes(state: dict) -> list[str]:
    """Build captions for failed fetches and successfully fetched stale data."""
    notes: list[str] = []
    for entry in state.get("stations", {}).values():
        name = entry.get("name", "Station")
        month = _fmt_month(entry.get("as_of"))
        if not entry.get("ok", True):
            if month:
                notes.append(f"{name} sea level data as of {month} (fetch pending)")
            else:
                notes.append(f"{name} sea level data (fetch pending)")
        elif entry.get("stale", False):
            if month:
                notes.append(
                    f"{name} sea level data as of {month} "
                    "(no later month passes coverage checks)"
                )
            else:
                notes.append(f"{name} sea level data (no recent month passes coverage checks)")
        filled = int(entry.get("interpolated_months", 0) or 0)
        longest = int(entry.get("longest_gap_months", 0) or 0)
        if filled and longest >= 6:
            notes.append(
                f"{name} sea level includes {filled} reconstructed missing months "
                f"(longest gap: {longest} months)"
            )

    return notes


def _patch_freshness(html: str, refreshed_label: str, stale_notes: list[str]) -> tuple[str, bool]:
    """
    Replace the content between the DATA_FRESHNESS markers in a page.

    Returns (new_html, patched_flag). Pages without the marker (any page but
    index.html) are left untouched.
    """
    inner = f"Data last refreshed: {refreshed_label} UTC"
    for note in stale_notes:
        inner += f'<br><span class="stale">{note}</span>'
    pattern = r"(<!--DATA_FRESHNESS-->).*?(<!--/DATA_FRESHNESS-->)"
    new_html, count = re.subn(
        pattern, lambda m: m.group(1) + inner + m.group(2), html, flags=re.DOTALL
    )
    return new_html, count > 0


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def _run_sst_nino12(cfg: dict, hn1: float, hn2: float, ndots: int,
                    out_dir: Path, win: dict) -> tuple[Path, dict]:
    """Run NINO1+2 absolute SST pipeline → stable filename."""
    dat = out_dir / "sva.2_filter_NINO12_SAIDApy.dat"
    result = pipeline.run_sst(
        local_file=cfg["sst"]["local_file"],
        ano_inicio=cfg["sst"]["ano_inicio"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
        window_start=win.get("start"), window_end=win.get("end"),
        base_year=int(win.get("base_year", 1975)),
    )
    result["output_file"] = str(dat)
    return dat, result


def _run_sst_index(cfg: dict, key: str, hn1: float, hn2: float, ndots: int,
                   out_dir: Path, win: dict) -> tuple[Path, dict]:
    """Run one SST anomaly index pipeline."""
    dat = out_dir / f"sva.2_filter_{key.upper()}_SAIDApy.dat"
    result = pipeline.run_sst_index(
        index_key=key,
        local_file=cfg["sst"]["local_file"],
        ano_inicio=cfg["sst"]["ano_inicio"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
        window_start=win.get("start"), window_end=win.get("end"),
        base_year=int(win.get("base_year", 1975)),
    )
    return dat, result


def _run_sl(st: dict, hn1: float, hn2: float, ndots: int,
            out_dir: Path, win: dict) -> tuple[Path, dict]:
    """Run sea level pipeline for one station."""
    dat = out_dir / f"sva.2_filter_{st['name']}_SAIDApy.dat"
    result = pipeline.run_sea_level(
        station_id=st["id"],
        station_name=st["name"],
        start_date=st["start_date"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
        rqd_url=st.get("rqd_url"),
        window_start=win.get("start"), window_end=win.get("end"),
        base_year=int(win.get("base_year", 1975)),
    )
    return dat, result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="update_website.py",
        description="Refresh ENSO data and re-embed JS arrays in all docs/*.html pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python scripts/update_website.py\n"
            "  python scripts/update_website.py --sst-only\n"
            "  python scripts/update_website.py --dry-run\n"
        ),
    )
    parser.add_argument(
        "--sst-only", action="store_true",
        help="Update only the SST (NINO1+2) array; skip all sea level stations",
    )
    parser.add_argument(
        "--sl-only", action="store_true",
        help="Update only the sea level stations; skip the SST/NINO pipelines "
             "(their existing JS blocks are left untouched)",
    )
    parser.add_argument(
        "--no-push", action="store_true",
        help="Update HTML files but skip the git add/commit/push step",
    )
    parser.add_argument(
        "--allow-older", action="store_true",
        help="Write the pages even if a dataset would move back to an earlier "
             "last month than the one already published (normally an error: it "
             "usually means a source was incomplete or a stale local cache was "
             "used, and writing would un-publish real observations)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run the pipeline and compute new arrays but do not write any files",
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="YAML config file (default: config.yaml)",
    )
    args = parser.parse_args()

    if args.sst_only and args.sl_only:
        print("ERROR: --sst-only and --sl-only are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)

    local_file = cfg["sst"]["local_file"]
    if not Path(local_file).exists():
        print(
            f"\nERROR: Historical SST file not found: {local_file}\n"
            f"This file contains NINO1+2 SST 1950–1981 and must be present.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hn1   = float(cfg["filter"]["HN1"])
    hn2   = float(cfg["filter"]["HN2"])
    ndots = int(cfg["filter"]["NDOTS"])
    # Fourier analysis window for the reference .dat files — config.yaml
    # filter.window. The website starts from the same defaults but lets the
    # visitor change them; see docs/assets/js/fourier-window.js.
    win   = cfg["filter"].get("window") or {}
    base_year = int(win.get("base_year", 1975))

    t0 = time.time()
    step = 1
    run_dt   = datetime.now(timezone.utc)
    run_date = run_dt.strftime("%Y-%m-%d")

    freshness = _load_freshness()
    loaded_data: dict[str, dict] = {}
    # Unfiltered monthly observations, embedded verbatim in the pages.
    loaded_raw: dict[str, dict] = {}
    # Most recent (year, month) of data seen, for the commit message.
    latest_ym: tuple[int, int] | None = None

    # ── SST pipelines ─────────────────────────────────────────────────────────
    # Skipped entirely under --sl-only: the SST/NINO JS blocks are simply left
    # out of loaded_raw, so the region keeps the values already published.
    sst_data = None
    sst_yr0 = sst_m0 = sst_yr1 = sst_m1 = sst_n = 0

    if not args.sl_only:
        print(f"[{step}] SST NINO1+2 pipeline (absolute) …"); step += 1
        sst_dat, sst_result = _run_sst_nino12(cfg, hn1, hn2, ndots, OUT_DIR, win)
        sst_data = _load_dat(str(sst_dat))
        loaded_raw["observedData"] = _as_raw(sst_result["raw_full"])
        sst_yr0 = int(sst_result["IYR"][0]);  sst_m0 = int(sst_result["MES"][0])
        sst_yr1 = int(sst_result["IYR"][-1]); sst_m1 = int(sst_result["MES"][-1])
        sst_n   = sum(1 for v in sst_data["irest"] if v == 0)
        latest_ym = (sst_yr1, sst_m1)
        print(f"  {_month_label(sst_yr0,sst_m0)} – {_month_label(sst_yr1,sst_m1)}  ({sst_n} months)")

        # Additional SST indices (anomaly)
        loaded_data["observedData"] = sst_data
        sst_idx_map = {idx["key"]: idx for idx in cfg.get("sst_indices", [])}
        for key in ("nino3", "nino4", "nino34"):
            if key not in sst_idx_map:
                continue
            label = sst_idx_map[key]["label"]
            print(f"[{step}] SST {label} pipeline (anomaly) …"); step += 1
            dat, idx_result = _run_sst_index(cfg, key, hn1, hn2, ndots, OUT_DIR, win)
            js_var = f"{key}Data"  # nino3Data, nino4Data, nino34Data
            loaded_data[js_var] = _load_dat(str(dat))
            loaded_raw[js_var] = _as_raw(idx_result["raw_full"])
            n = sum(1 for v in loaded_data[js_var]["irest"] if v == 0)
            print(f"  {label}: {n} months")
    else:
        print(f"[{step}] Skipping SST pipelines (--sl-only); existing blocks kept."); step += 1

    # ── Sea level pipelines ───────────────────────────────────────────────────
    cal_data = None
    cal_yr0 = cal_m0 = cal_yr1 = cal_m1 = cal_n = 0

    # Station key → JS variable name
    _sl_var = {
        "callao":       "callaoData",
        "la_libertad":  "laLibData",
        "honolulu":     "honoluluData",
        "palau":        "palauData",
    }

    failed_stations: list[str] = []

    if not args.sst_only:
        for key, st in cfg["stations"].items():
            js_var = _sl_var.get(key, f"{key}Data")
            print(f"[{step}] {st['name']} sea level pipeline …"); step += 1
            try:
                dat, result = _run_sl(st, hn1, hn2, ndots, OUT_DIR, win)
                loaded_data[js_var] = _load_dat(str(dat))
                loaded_raw[js_var] = _as_raw(result["raw_full"])
                n = sum(1 for v in loaded_data[js_var]["irest"] if v == 0)
                yr0 = int(result["IYR"][0]);  m0 = int(result["MES"][0])
                yr1 = int(result["IYR"][-1]); m1 = int(result["MES"][-1])
                print(f"  {_month_label(yr0,m0)} – {_month_label(yr1,m1)}  ({n} months)")
                latest_ym = max(latest_ym or (yr1, m1), (yr1, m1))
                lag_months = (run_dt.year * 12 + run_dt.month) - (yr1 * 12 + m1)
                # Record a fresh, successful fetch for this station.
                freshness["stations"][key] = {
                    "name": st["name"],
                    "last_success": run_date,
                    "as_of": f"{yr1}-{m1:02d}",
                    "ok": True,
                    "stale": lag_months > STALE_AFTER_MONTHS,
                    "interpolated_months": result.get("interpolated_months", 0),
                    "low_coverage_months": result.get("low_coverage_months", 0),
                    "longest_gap_months": result.get("longest_gap_months", 0),
                    "preliminary_month": result.get("preliminary_month", False),
                }
                if key == "callao":
                    cal_data  = loaded_data[js_var]
                    cal_yr0, cal_m0, cal_yr1, cal_m1, cal_n = yr0, m0, yr1, m1, n
            except RuntimeError as exc:
                # A single flaky station (e.g. Callao when UHSLC times out) must
                # not abort the whole update. Skip it: without its entry in
                # loaded_raw, the rebuilt region reuses the values already on
                # the page (stale but not broken), and — for Callao —
                # cal_data stays None so _patch_stats_bar is skipped entirely.
                print(
                    f"  WARNING: {st['name']} sea level pipeline failed; "
                    f"leaving its existing data in place.\n"
                    f"  {exc}",
                    file=sys.stderr,
                )
                failed_stations.append(st["name"])
                # Mark stale but preserve the last-known-good date/month so the
                # freshness footnote can say "as of <month> (fetch pending)".
                prev = freshness["stations"].get(key, {})
                freshness["stations"][key] = {
                    "name": st["name"],
                    "last_success": prev.get("last_success"),
                    "as_of": prev.get("as_of"),
                    "ok": False,
                    "stale": True,
                    "interpolated_months": prev.get("interpolated_months", 0),
                    "low_coverage_months": prev.get("low_coverage_months", 0),
                    "longest_gap_months": prev.get("longest_gap_months", 0),
                    "preliminary_month": prev.get("preliminary_month", False),
                }
                continue

    # ── Freshness bookkeeping ─────────────────────────────────────────────────
    freshness["last_refreshed"] = run_date
    if not args.dry_run:
        _save_freshness(freshness)
    refreshed_label = _fmt_run_date(run_dt)
    stale_notes     = _stale_notes(freshness)
    if stale_notes:
        print("  Freshness: " + "; ".join(stale_notes))

    # ── Patch all HTML files ──────────────────────────────────────────────────
    print(f"[{step}] Patching HTML files …"); step += 1

    patched_files: list[Path] = []
    # Pages are rendered first and written only once every one of them has
    # passed the no-regression check, so a single bad dataset cannot leave
    # half the site updated and half rolled back.
    pending: list[tuple[Path, str]] = []
    regressions: list[str] = []
    for html_path in HTML_FILES:
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        original = html

        # Rebuild the whole generated region. Datasets that were not re-run
        # this time (--sst-only / --sl-only, or a station that failed) keep
        # the values already published on the page.
        published = _extract_raw_series(html)
        page_raw: "OrderedDict[str, dict]" = OrderedDict()
        for var_name in DATASETS:
            if var_name in loaded_raw:
                page_raw[var_name] = loaded_raw[var_name]
            elif var_name in published:
                page_raw[var_name] = published[var_name]
        if page_raw:
            regressions += _check_no_regression(html_path.name, loaded_raw, published)
            region = _build_data_region(page_raw, hn1, hn2, ndots, base_year)
            html, patched = _patch_data_region(html, region)
            if not patched and html_path.name != "index.html":
                print(f"  WARNING: no data region found in {html_path}", file=sys.stderr)

        # Stats bar update (index.html only, only when both SST and Callao present)
        if (html_path.name == "index.html"
                and sst_data is not None and cal_data is not None):
            html = _patch_stats_bar(
                html,
                sst_yr0, sst_m0, sst_yr1, sst_m1, sst_n,
                cal_yr0, cal_m0, cal_yr1, cal_m1, cal_n,
            )

        # Patch every page that opts in with DATA_FRESHNESS markers.
        html, _ = _patch_freshness(html, refreshed_label, stale_notes)

        if html == original:
            print(f"  Unchanged: {html_path}")
            continue
        pending.append((html_path, html))

    # ── Regression guard ──────────────────────────────────────────────────
    if regressions:
        for line in regressions:
            print(f"  {'WARNING' if args.allow_older else 'ERROR'}: {line}",
                  file=sys.stderr)
        if not args.allow_older:
            print(
                "\nRefusing to write: the new data ends earlier than what is "
                "already published.\nCheck that every source was reachable "
                "(data/input/ may hold a stale cache), then re-run.\n"
                "Pass --allow-older only if the older record is genuinely the "
                "correct one.",
                file=sys.stderr,
            )
            sys.exit(1)

    for html_path, html in pending:
        if not args.dry_run:
            html_path.write_text(html, encoding="utf-8")
            print(f"  Written:   {html_path}")
            patched_files.append(html_path)
        else:
            print(f"  [dry-run] Would write: {html_path}")

    # ── Git push ──────────────────────────────────────────────────────────────
    if not args.dry_run and not args.no_push and patched_files:
        print(f"[{step}] Committing and pushing …"); step += 1
        if latest_ym is not None:
            month_str = f"{latest_ym[0]}-{latest_ym[1]:02d}"
        else:
            month_str = run_dt.strftime("%Y-%m")
        msg = f"data: update ENSO arrays through {month_str} [auto]"
        add_targets = [str(p) for p in patched_files]
        cmds = [
            ["git", "add"] + add_targets,
            ["git", "commit", "-m", msg],
            ["git", "push"],
        ]
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  WARNING: {' '.join(cmd[:2])} exited {r.returncode}")
                print(f"  stderr: {r.stderr.strip()}")
                break
            print(f"  OK: {' '.join(cmd[:2])}")

    if failed_stations:
        print(
            f"\nWARNING: {len(failed_stations)} sea level station(s) failed "
            f"and kept their previous data: {', '.join(failed_stations)}",
            file=sys.stderr,
        )

    print(f"\nDone in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
