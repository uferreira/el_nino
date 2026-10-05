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
import os
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
#   js_var -> (dat_filename, length_constant, label, unit, group, deseasonalize,
#              cfg_key)
# "deseasonalize" mirrors the Python pipeline: absolute series have their
# monthly climatology removed before the filter and added back afterwards;
# the NOAA NINO3/4/3.4 columns are already anomalies and are filtered as-is.
# "cfg_key" is the config.yaml key (sst_indices[].key or stations.<key>) the
# series comes from. main() refuses to run if config.yaml lists a dataset
# that has no entry here, because the page region is built from this table
# and such a dataset would otherwise be processed but never published.
DATASETS: OrderedDict[str, dict] = OrderedDict([
    ("observedData", dict(dat="sva.2_filter_NINO12_SAIDApy.dat",      len="OBS_N",
                          label="NINO1+2 SST",    unit="\u00b0C", group="sst", deseasonalize=True,
                          cfg_key="nino12")),
    ("nino3Data",    dict(dat="sva.2_filter_NINO3_SAIDApy.dat",       len="NINO3_N",
                          label="NINO3 anomaly",  unit="\u00b0C", group="sst", deseasonalize=False,
                          cfg_key="nino3")),
    ("nino4Data",    dict(dat="sva.2_filter_NINO4_SAIDApy.dat",       len="NINO4_N",
                          label="NINO4 anomaly",  unit="\u00b0C", group="sst", deseasonalize=False,
                          cfg_key="nino4")),
    ("nino34Data",   dict(dat="sva.2_filter_NINO34_SAIDApy.dat",      len="NINO34_N",
                          label="NINO3.4 anomaly", unit="\u00b0C", group="sst", deseasonalize=False,
                          cfg_key="nino34")),
    ("callaoData",   dict(dat="sva.2_filter_Callao_SAIDApy.dat",      len="CAL_N",
                          label="Callao SL",      unit="mm", group="sl", deseasonalize=True,
                          cfg_key="callao")),
    ("laLibData",    dict(dat="sva.2_filter_La Libertad_SAIDApy.dat", len="LALIB_N",
                          label="La Libertad SL", unit="mm", group="sl", deseasonalize=True,
                          cfg_key="la_libertad")),
    ("honoluluData", dict(dat="sva.2_filter_Honolulu_SAIDApy.dat",    len="HON_N",
                          label="Honolulu SL",    unit="mm", group="sl", deseasonalize=True,
                          cfg_key="honolulu")),
    ("palauData",    dict(dat="sva.2_filter_Palau_SAIDApy.dat",       len="PAL_N",
                          label="Palau SL",       unit="mm", group="sl", deseasonalize=True,
                          cfg_key="palau")),
])


def _js_var_for(group: str, cfg_key: str) -> str | None:
    """RAW_SERIES variable for a config.yaml dataset, or None if unmapped."""
    for var_name, meta in DATASETS.items():
        if meta["group"] == group and meta["cfg_key"] == cfg_key:
            return var_name
    return None


def _sst_indices(cfg: dict) -> list[tuple[str, str]]:
    """(key, label) of every SST series a run processes, NINO1+2 first.

    NINO1+2 (absolute SST) is the site's primary series and always runs from
    config.yaml ``sst``; the other indices come from ``sst_indices``.
    """
    labels = {idx["key"]: idx.get("label", idx["key"])
              for idx in cfg.get("sst_indices", [])}
    out = [("nino12", labels.pop("nino12", "NINO1+2"))]
    return out + list(labels.items())


def _unmapped_config_datasets(cfg: dict) -> list[str]:
    """config.yaml datasets that DATASETS cannot publish (config drift)."""
    problems = [
        f"sst_indices key {idx['key']!r}"
        for idx in cfg.get("sst_indices", [])
        if _js_var_for("sst", idx["key"]) is None
    ]
    problems += [
        f"station {key!r}"
        for key in (cfg.get("stations") or {})
        if _js_var_for("sl", key) is None
    ]
    return problems

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
            state.setdefault("sst", {})
            return state
    except (FileNotFoundError, ValueError, OSError):
        pass
    return {"sst": {}, "stations": {}}


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


def _refreshed_label(state: dict) -> str:
    """
    Footer line with the newest successful refresh of each part, e.g.
    'Data last refreshed: SST 5 October 2026, sea level 6 October 2026 (UTC)'.

    SST (CI) and sea level (local script) are updated separately, so each part
    carries its own date.
    """
    parts = []
    for section, label in (("sst", "SST"), ("stations", "sea level")):
        dates = [e["last_success"] for e in state.get(section, {}).values()
                 if e.get("last_success")]
        if dates:
            dt = datetime.strptime(max(dates), "%Y-%m-%d")
            parts.append(f"{label} {_fmt_run_date(dt)}")
    return "Data last refreshed: " + (", ".join(parts) + " (UTC)" if parts else "never")


def _stale_notes(state: dict) -> list[str]:
    """Build captions for failed fetches and successfully fetched stale data."""
    notes: list[str] = []
    for entry in state.get("sst", {}).values():
        if not entry.get("ok", True):
            month = _fmt_month(entry.get("as_of"))
            name = entry.get("name", "SST")
            notes.append(f"{name} data as of {month} (fetch pending)" if month
                         else f"{name} data (fetch pending)")
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
    inner = refreshed_label
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
# Run summary and silent-skip guard
# ---------------------------------------------------------------------------

def _gh_annotation(level: str, message: str) -> None:
    """Surface a problem in the GitHub Actions run summary (no-op locally)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{message}")


def _silently_skipped(cfg: dict, freshness: dict, run_stamp: str,
                      *, sst: bool, sl: bool) -> list[str]:
    """Configured datasets this run should have processed but did not record.

    A dataset counts as handled when its freshness.json entry carries this
    run's ``last_attempt`` stamp, as a success or as a failure. Checking the
    persisted state, rather than
    the loop that produced it, is what makes a skipped dataset impossible to
    miss: whatever path skipped it also failed to record it.
    """
    missing: list[str] = []
    wanted = []
    if sst:
        wanted += [("sst", key, label) for key, label in _sst_indices(cfg)]
    if sl:
        wanted += [("stations", key, st["name"])
                   for key, st in (cfg.get("stations") or {}).items()]
    for section, key, name in wanted:
        entry = freshness.get(section, {}).get(key) or {}
        if entry.get("last_attempt") != run_stamp:
            missing.append(name)
    return missing


def _print_summary(rows: "OrderedDict[str, dict]") -> None:
    """One row per dataset: source, first/last month, months, status."""
    headers = ("Dataset", "Source", "First", "Last", "Months", "Status")
    table = [headers] + [
        (r["name"], r["source"], r["first"], r["last"], str(r["n"]), r["status"])
        for r in rows.values()
    ]
    widths = [max(len(row[i]) for row in table) for i in range(len(headers) - 1)]
    print("\nUpdate summary")
    for i, row in enumerate(table):
        cells = [c.ljust(w) for c, w in zip(row, widths)] + [row[-1]]
        print("  " + "  ".join(cells))
        if i == 0:
            print("  " + "  ".join("-" * w for w in widths) + "  " + "-" * 6)


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

    run_stamp = run_dt.isoformat(timespec="seconds")
    # Optional wall-clock budget (seconds) for the downloads, set by CI. Once
    # it is spent, the remaining datasets are recorded as failed rather than
    # attempted, so the job finishes, publishes what it has and says what it
    # skipped, instead of being killed by the job timeout with nothing saved.
    budget = float(os.environ.get("ENSO_UPDATE_BUDGET_S") or 0)

    def _budget_spent() -> RuntimeError | None:
        if budget and time.time() - t0 > budget:
            return RuntimeError(f"time budget of {budget:.0f}s exhausted; not attempted")
        return None
    unmapped = _unmapped_config_datasets(cfg)
    if unmapped:
        print(
            "ERROR: config.yaml lists datasets that update_website.DATASETS cannot "
            "publish: " + ", ".join(unmapped) + "\nAdd them to DATASETS (and to "
            "the pages) or remove them from config.yaml.",
            file=sys.stderr,
        )
        sys.exit(1)

    freshness = _load_freshness()
    # Unfiltered monthly observations, embedded verbatim in the pages.
    loaded_raw: dict[str, dict] = {}
    # One summary row per configured dataset, filled in as it is processed.
    rows: "OrderedDict[str, dict]" = OrderedDict()
    # Most recent (year, month) of data seen, for the commit message.
    latest_ym: tuple[int, int] | None = None

    def _record_success(js_var: str, name: str, source: str, raw: dict,
                        status: str = "updated") -> tuple[int, int]:
        nonlocal latest_ym
        y0, m0 = int(raw["year"][0]), int(raw["month"][0])
        y1, m1 = int(raw["year"][-1]), int(raw["month"][-1])
        rows[js_var] = dict(name=name, source=source,
                            first=f"{y0}-{m0:02d}", last=f"{y1}-{m1:02d}",
                            n=len(raw["values"]), status=status)
        latest_ym = max(latest_ym or (y1, m1), (y1, m1))
        print(f"  {_month_label(y0, m0)} – {_month_label(y1, m1)}  "
              f"({len(raw['values'])} months, {source})")
        return y1, m1

    def _record_failure(js_var: str, name: str, section: str, key: str,
                        exc: Exception) -> None:
        # One flaky source must not abort the whole update. Without an entry
        # in loaded_raw, the rebuilt region reuses the values already on the
        # page (stale but not broken). The failure is recorded so the
        # freshness footnote can say "as of <month> (fetch pending)" and the
        # summary table shows it.
        print(f"  WARNING: {name} pipeline failed; leaving its existing data "
              f"in place.\n  {exc}", file=sys.stderr)
        prev = freshness[section].get(key, {})
        entry = dict(prev)
        entry.update(name=name, last_attempt=run_stamp,
                     last_success=prev.get("last_success"),
                     as_of=prev.get("as_of"), ok=False, stale=True)
        freshness[section][key] = entry
        reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        rows[js_var] = dict(name=name, source="-", first="-",
                            last=prev.get("as_of") or "-", n="-",
                            status=f"FAILED: {reason[:60]}")
        _gh_annotation("warning", f"{name}: update failed, previous data kept: {reason}")

    # ── SST pipelines ─────────────────────────────────────────────────────────
    # NINO1+2 is filtered as absolute SST, every other index in config.yaml
    # sst_indices as a NOAA anomaly. All four share one NOAA download
    # (download.load_sst caches it for the life of the process).
    for key, label in _sst_indices(cfg):
        js_var = _js_var_for("sst", key)
        if args.sl_only:
            rows[js_var] = dict(name=label, source="-", first="-", last="-",
                                n="-", status="skipped (--sl-only)")
            continue
        if (spent := _budget_spent()) is not None:
            _record_failure(js_var, label, "sst", key, spent)
            continue
        kind = "absolute" if key == "nino12" else "anomaly"
        print(f"[{step}] SST {label} pipeline ({kind}) …"); step += 1
        try:
            if key == "nino12":
                _, result = _run_sst_nino12(cfg, hn1, hn2, ndots, OUT_DIR, win)
            else:
                _, result = _run_sst_index(cfg, key, hn1, hn2, ndots, OUT_DIR, win)
        except RuntimeError as exc:
            _record_failure(js_var, label, "sst", key, exc)
            continue
        loaded_raw[js_var] = _as_raw(result["raw_full"])
        y1, m1 = _record_success(js_var, label, "NOAA CPC", loaded_raw[js_var])
        freshness["sst"][key] = {
            "name": label,
            "last_attempt": run_stamp,
            "last_success": run_date,
            "as_of": f"{y1}-{m1:02d}",
            "ok": True,
        }

    # ── Sea level pipelines ───────────────────────────────────────────────────
    for key, st in (cfg.get("stations") or {}).items():
        js_var = _js_var_for("sl", key)
        if args.sst_only:
            rows[js_var] = dict(name=st["name"], source="-", first="-", last="-",
                                n="-", status="skipped (--sst-only)")
            continue
        if (spent := _budget_spent()) is not None:
            _record_failure(js_var, st["name"], "stations", key, spent)
            continue
        print(f"[{step}] {st['name']} sea level pipeline …"); step += 1
        try:
            _, result = _run_sl(st, hn1, hn2, ndots, OUT_DIR, win)
        except RuntimeError as exc:
            _record_failure(js_var, st["name"], "stations", key, exc)
            continue
        loaded_raw[js_var] = _as_raw(result["raw_full"])
        raw = loaded_raw[js_var]
        y1, m1 = int(raw["year"][-1]), int(raw["month"][-1])
        status = "updated"
        # The newest month must not be lost between download and publication:
        # the source serves observations up to `served_through`, and only the
        # month after the last published one may legitimately be missing
        # (it can still be in progress or below the coverage threshold).
        served = result.get("served_through")
        if served:
            sy, sm = (int(v) for v in served.split("-"))
            behind = (sy * 12 + sm) - (y1 * 12 + m1)
            if behind > 1:
                status = f"updated, LAGS source ({served})"
                print(f"  WARNING: {st['name']} ends {y1}-{m1:02d} but UHSLC "
                      f"serves observations through {served}", file=sys.stderr)
                _gh_annotation("warning", f"{st['name']} ends {y1}-{m1:02d}; "
                               f"UHSLC serves data through {served}")
        _record_success(js_var, st["name"], result.get("source") or "?", raw,
                        status=status)
        lag_months = (run_dt.year * 12 + run_dt.month) - (y1 * 12 + m1)
        freshness["stations"][key] = {
            "name": st["name"],
            "last_attempt": run_stamp,
            "last_success": run_date,
            "as_of": f"{y1}-{m1:02d}",
            "ok": True,
            "stale": lag_months > STALE_AFTER_MONTHS,
            "source": result.get("source"),
            "interpolated_months": result.get("interpolated_months", 0),
            "low_coverage_months": result.get("low_coverage_months", 0),
            "longest_gap_months": result.get("longest_gap_months", 0),
            "preliminary_month": result.get("preliminary_month", False),
        }

    # ── Silent-skip guard ─────────────────────────────────────────────────────
    # Every configured dataset this run was asked to process must end up either
    # refreshed today or recorded as failed. Anything else means a code path
    # skipped it without saying so, which is how a stale site goes unnoticed.
    silent = _silently_skipped(cfg, freshness, run_stamp,
                               sst=not args.sl_only, sl=not args.sst_only)
    if silent:
        _print_summary(rows)
        for name in silent:
            print(f"ERROR: {name} was neither updated nor recorded as failed.",
                  file=sys.stderr)
            _gh_annotation("error", f"{name} was silently skipped")
        sys.exit(1)

    # ── Freshness bookkeeping ─────────────────────────────────────────────────
    # The footer date comes from each dataset's own last_success, so an
    # --sst-only or --sl-only run moves the date of the part it refreshed.
    freshness.pop("last_refreshed", None)   # superseded by per-part dates
    if not args.dry_run:
        _save_freshness(freshness)
    refreshed_label = _refreshed_label(freshness)
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
        # this time (--sst-only / --sl-only, or a source that failed) keep
        # the values already published on the page.
        if DATA_BEGIN in html or _LEGACY_REGION.search(html):
            published = _extract_raw_series(html)
            page_raw: "OrderedDict[str, dict]" = OrderedDict()
            for var_name in DATASETS:
                if var_name in loaded_raw:
                    page_raw[var_name] = loaded_raw[var_name]
                elif var_name in published:
                    page_raw[var_name] = published[var_name]
            regressions += _check_no_regression(html_path.name, loaded_raw, published)
            region = _build_data_region(page_raw, hn1, hn2, ndots, base_year)
            html, _ = _patch_data_region(html, region)
        elif html_path.name != "index.html":
            print(f"  WARNING: no data region found in {html_path}", file=sys.stderr)

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
                "and up to date, then re-run.\n"
                "Pass --allow-older only if the older record is genuinely the "
                "correct one.",
                file=sys.stderr,
            )
            _print_summary(rows)
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
            # data/output/ is gitignored, but the freshness state must travel
            # with the pages or the next checkout starts from an old one.
            ["git", "add", "-f", str(FRESHNESS_FILE)],
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

    _print_summary(rows)
    failed = [r["name"] for r in rows.values() if r["status"].startswith("FAILED")]
    if failed:
        print(
            f"\nWARNING: {len(failed)} dataset(s) failed and kept their "
            f"previous data: {', '.join(failed)}",
            file=sys.stderr,
        )

    print(f"\nDone in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
