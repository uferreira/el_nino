"""
scripts/update_website.py
=========================
Download fresh ENSO data, re-run the Fourier filter pipeline, and
re-embed the JS data arrays in all docs/*.html pages.

Run from the project root:

    python scripts/update_website.py              # all datasets
    python scripts/update_website.py --sst-only   # only NINO1+2 SST
    python scripts/update_website.py --dry-run    # compute but do not write
    python scripts/update_website.py --no-push    # update HTML but skip git push

Each HTML page that contains a JS block of the form:

    const <varName> = { x:[...], y:[...], year:[...], month:[...], irest:[...] };
    const <LEN_VAR> = <varName>.x.length;  // <N>

will have that block replaced with fresh data from the corresponding .dat file.
Pages that do not contain a given block are left unchanged.

Dataset → JS variable mapping
------------------------------
    sva.2_filter_NINO12_SAIDApy.dat   → observedData  / OBS_N
    sva.2_filter_NINO3_SAIDApy.dat    → nino3Data     / NINO3_N
    sva.2_filter_NINO4_SAIDApy.dat    → nino4Data     / NINO4_N
    sva.2_filter_NINO34_SAIDApy.dat   → nino34Data    / NINO34_N
    sva.2_filter_Callao_SAIDApy.dat   → callaoData    / CAL_N
    sva.2_filter_Talara_SAIDApy.dat   → talaraData    / TAL_N
    sva.2_filter_La Libertad_SAIDApy.dat → laLibData  / LALIB_N
    sva.2_filter_Honolulu_SAIDApy.dat → honoluluData  / HON_N
    sva.2_filter_Palau_SAIDApy.dat    → palauData     / PAL_N
"""

import argparse
import re
import subprocess
import sys
import time
from collections import OrderedDict
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

OUT_DIR = Path("data/output")
CONFIG  = Path("config.yaml")
DOCS    = Path("docs")

# All known datasets: var_name → (dat_filename, length_constant_name)
DATASETS: OrderedDict[str, tuple[str, str]] = OrderedDict([
    ("observedData", ("sva.2_filter_NINO12_SAIDApy.dat",        "OBS_N")),
    ("nino3Data",    ("sva.2_filter_NINO3_SAIDApy.dat",         "NINO3_N")),
    ("nino4Data",    ("sva.2_filter_NINO4_SAIDApy.dat",         "NINO4_N")),
    ("nino34Data",   ("sva.2_filter_NINO34_SAIDApy.dat",        "NINO34_N")),
    ("callaoData",   ("sva.2_filter_Callao_SAIDApy.dat",        "CAL_N")),
    ("talaraData",   ("sva.2_filter_Talara_SAIDApy.dat",        "TAL_N")),
    ("laLibData",    ("sva.2_filter_La Libertad_SAIDApy.dat",   "LALIB_N")),
    ("honoluluData", ("sva.2_filter_Honolulu_SAIDApy.dat",      "HON_N")),
    ("palauData",    ("sva.2_filter_Palau_SAIDApy.dat",         "PAL_N")),
])

# All HTML pages to patch (skipped silently if not found)
HTML_FILES = [
    DOCS / "index.html",
    DOCS / "animations.html",
    DOCS / "familiar_attractor.html",
    DOCS / "ensemble.html",
    DOCS / "compare.html",
]


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


def _build_js_block(var_name: str, len_var: str, data: dict) -> str:
    """Return the two-line JS const block for a dataset."""
    x_arr  = _compact_array(data["x"],     ".2f")
    y_arr  = _compact_array(data["y"],     ".2f")
    yr_arr = _compact_array(data["year"],  "d")
    mo_arr = _compact_array(data["month"], "d")
    ir_arr = _compact_array(data["irest"], "d")
    n      = len(data["x"])
    return (
        f"const {var_name} = {{\n"
        f"  x:     {x_arr},\n"
        f"  y:     {y_arr},\n"
        f"  year:  {yr_arr},\n"
        f"  month: {mo_arr},\n"
        f"  irest: {ir_arr}\n"
        f"}};\n"
        f"const {len_var} = {var_name}.x.length;  // {n}"
    )


def _patch_dataset(html: str, var_name: str, len_var: str, data: dict) -> tuple[str, bool]:
    """
    Replace a single JS dataset block in an HTML string.

    Returns (new_html, patched_flag). Returns html unchanged if the pattern
    is not present (so pages that don't use a dataset are left untouched).
    """
    new_block = _build_js_block(var_name, len_var, data)
    pattern = (
        rf"const {re.escape(var_name)}\s*=\s*\{{.*?\}};\s*\n"
        rf"const {re.escape(len_var)}\s*=\s*[^\n]+"
    )
    new_html, count = re.subn(pattern, new_block, html, flags=re.DOTALL)
    return new_html, count > 0


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
# Pipeline runners
# ---------------------------------------------------------------------------

def _run_sst_nino12(cfg: dict, hn1: float, hn2: float, ndots: int,
                    out_dir: Path) -> tuple[Path, dict]:
    """Run NINO1+2 absolute SST pipeline → stable filename."""
    dat = out_dir / "sva.2_filter_NINO12_SAIDApy.dat"
    result = pipeline.run_sst(
        local_file=cfg["sst"]["local_file"],
        ano_inicio=cfg["sst"]["ano_inicio"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
    )
    result["output_file"] = str(dat)
    return dat, result


def _run_sst_index(cfg: dict, key: str, hn1: float, hn2: float, ndots: int,
                   out_dir: Path) -> tuple[Path, dict]:
    """Run one SST anomaly index pipeline."""
    dat = out_dir / f"sva.2_filter_{key.upper()}_SAIDApy.dat"
    result = pipeline.run_sst_index(
        index_key=key,
        local_file=cfg["sst"]["local_file"],
        ano_inicio=cfg["sst"]["ano_inicio"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
    )
    return dat, result


def _run_sl(st: dict, hn1: float, hn2: float, ndots: int,
            out_dir: Path) -> tuple[Path, dict]:
    """Run sea level pipeline for one station."""
    dat = out_dir / f"sva.2_filter_{st['name']}_SAIDApy.dat"
    result = pipeline.run_sea_level(
        station_id=st["id"],
        station_name=st["name"],
        start_date=st["start_date"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
        rqd_url=st.get("rqd_url"),
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
        "--no-push", action="store_true",
        help="Update HTML files but skip the git add/commit/push step",
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

    t0 = time.time()
    step = 1

    # ── SST pipelines ─────────────────────────────────────────────────────────
    print(f"[{step}] SST NINO1+2 pipeline (absolute) …"); step += 1
    sst_dat, sst_result = _run_sst_nino12(cfg, hn1, hn2, ndots, OUT_DIR)
    sst_data = _load_dat(str(sst_dat))
    sst_yr0 = int(sst_result["IYR"][0]);  sst_m0 = int(sst_result["MES"][0])
    sst_yr1 = int(sst_result["IYR"][-1]); sst_m1 = int(sst_result["MES"][-1])
    sst_n   = sum(1 for v in sst_data["irest"] if v == 0)
    print(f"  {_month_label(sst_yr0,sst_m0)} – {_month_label(sst_yr1,sst_m1)}  ({sst_n} months)")

    # Additional SST indices (anomaly)
    loaded_data: dict[str, dict] = {"observedData": sst_data}
    sst_idx_map = {idx["key"]: idx for idx in cfg.get("sst_indices", [])}
    for key in ("nino3", "nino4", "nino34"):
        if key not in sst_idx_map:
            continue
        label = sst_idx_map[key]["label"]
        print(f"[{step}] SST {label} pipeline (anomaly) …"); step += 1
        dat, _ = _run_sst_index(cfg, key, hn1, hn2, ndots, OUT_DIR)
        js_var = f"{key}Data"  # nino3Data, nino4Data, nino34Data
        loaded_data[js_var] = _load_dat(str(dat))
        n = sum(1 for v in loaded_data[js_var]["irest"] if v == 0)
        print(f"  {label}: {n} months")

    # ── Sea level pipelines ───────────────────────────────────────────────────
    cal_data = None
    cal_yr0 = cal_m0 = cal_yr1 = cal_m1 = cal_n = 0

    # Station key → JS variable name
    _sl_var = {
        "callao":       "callaoData",
        "talara":       "talaraData",
        "la_libertad":  "laLibData",
        "honolulu":     "honoluluData",
        "palau":        "palauData",
    }

    if not args.sst_only:
        for key, st in cfg["stations"].items():
            js_var = _sl_var.get(key, f"{key}Data")
            print(f"[{step}] {st['name']} sea level pipeline …"); step += 1
            dat, result = _run_sl(st, hn1, hn2, ndots, OUT_DIR)
            loaded_data[js_var] = _load_dat(str(dat))
            n = sum(1 for v in loaded_data[js_var]["irest"] if v == 0)
            yr0 = int(result["IYR"][0]);  m0 = int(result["MES"][0])
            yr1 = int(result["IYR"][-1]); m1 = int(result["MES"][-1])
            print(f"  {_month_label(yr0,m0)} – {_month_label(yr1,m1)}  ({n} months)")
            if key == "callao":
                cal_data  = loaded_data[js_var]
                cal_yr0, cal_m0, cal_yr1, cal_m1, cal_n = yr0, m0, yr1, m1, n

    # ── Patch all HTML files ──────────────────────────────────────────────────
    print(f"[{step}] Patching HTML files …"); step += 1

    patched_files: list[Path] = []
    for html_path in HTML_FILES:
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        original = html
        for var_name, data in loaded_data.items():
            _, len_var = DATASETS[var_name]
            html, _ = _patch_dataset(html, var_name, len_var, data)

        # Stats bar update (index.html only, only when both SST and Callao present)
        if html_path.name == "index.html" and cal_data is not None:
            html = _patch_stats_bar(
                html,
                sst_yr0, sst_m0, sst_yr1, sst_m1, sst_n,
                cal_yr0, cal_m0, cal_yr1, cal_m1, cal_n,
            )

        if html == original:
            print(f"  Unchanged: {html_path}")
            continue

        if not args.dry_run:
            html_path.write_text(html, encoding="utf-8")
            print(f"  Written:   {html_path}")
            patched_files.append(html_path)
        else:
            print(f"  [dry-run] Would write: {html_path}")

    # ── Git push ──────────────────────────────────────────────────────────────
    if not args.dry_run and not args.no_push and patched_files:
        print(f"[{step}] Committing and pushing …"); step += 1
        month_str = f"{sst_yr1}-{sst_m1:02d}"
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

    print(f"\nDone in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
