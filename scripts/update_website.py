"""
scripts/update_website.py
=========================
Download fresh ENSO data, re-run the Fourier filter pipeline, and
re-embed the JS data arrays in docs/index.html.

Run from the project root:

    python scripts/update_website.py              # SST + all sea level stations
    python scripts/update_website.py --sst-only   # only NINO1+2 SST
    python scripts/update_website.py --dry-run    # compute but do not write
    python scripts/update_website.py --no-push    # update HTML but skip git push

The script patches two JS constant blocks in docs/index.html:

    const observedData = { x:[...], y:[...], year:[...], month:[...], irest:[...] };
    const OBS_N = observedData.x.length;  // <N>

    const callaoData   = { x:[...], y:[...], year:[...], month:[...], irest:[...] };
    const CAL_N  = callaoData.x.length;   // <N>

It also updates the human-readable stats in the HTML header band:
    <strong>Jan 1975 – Apr 2026</strong>   (SST date range)
    <strong>3,076</strong>                  (SST point count)
    <strong>Jan 1970 – Mar 2026</strong>   (Callao date range)
    <strong>3,361</strong>                  (Callao point count)
"""

import argparse
import glob
import re
import subprocess
import sys
import time
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

INDEX_HTML = Path("docs/index.html")
OUT_DIR    = Path("data/output")
CONFIG     = Path("config.yaml")


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
    x_arr    = _compact_array(data["x"],      ".2f")
    y_arr    = _compact_array(data["y"],      ".2f")
    yr_arr   = _compact_array(data["year"],   "d")
    mo_arr   = _compact_array(data["month"],  "d")
    ir_arr   = _compact_array(data["irest"],  "d")
    n        = len(data["x"])
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


def _patch_html(html: str, obs_data: dict | None, cal_data: dict | None,
                sst_yr0: int, sst_m0: int, sst_yr1: int, sst_m1: int,
                cal_yr0: int, cal_m0: int, cal_yr1: int, cal_m1: int) -> str:
    """
    Replace the embedded JS arrays and human-readable date/count spans.

    Returns the patched HTML string.
    """
    # ── JS data blocks ────────────────────────────────────────────────────────
    if obs_data is not None:
        # Replace from "const observedData = {" to "const OBS_N = …"
        new_obs = _build_js_block("observedData", "OBS_N", obs_data)
        html = re.sub(
            r"const observedData\s*=\s*\{.*?\};\s*\nconst OBS_N\s*=\s*[^\n]+",
            new_obs,
            html,
            flags=re.DOTALL,
        )

    if cal_data is not None:
        new_cal = _build_js_block("callaoData", "CAL_N", cal_data)
        html = re.sub(
            r"const callaoData\s*=\s*\{.*?\};\s*\nconst CAL_N\s*=\s*[^\n]+",
            new_cal,
            html,
            flags=re.DOTALL,
        )

    # ── Stats bar: SST ────────────────────────────────────────────────────────
    if obs_data is not None:
        obs_range = f"{_month_label(sst_yr0, sst_m0)} – {_month_label(sst_yr1, sst_m1)}"
        obs_pts   = _pts_label(len(obs_data["x"]))
        # Period span in Section 1 stats-bar
        html = re.sub(
            r"(Period:\s*<strong>)([^<]+)(</strong>)",
            lambda m: m.group(1) + obs_range + m.group(3),
            html,
            count=1,
        )
        # Points span in Section 1 stats-bar (first occurrence of N,NNN pattern after "Points:")
        html = re.sub(
            r"(Points:\s*<strong>)([\d,]+)(</strong>)",
            lambda m: m.group(1) + obs_pts + m.group(3),
            html,
            count=1,
        )

    # ── Stats bar: Callao ─────────────────────────────────────────────────────
    if cal_data is not None:
        cal_range = f"{_month_label(cal_yr0, cal_m0)} – {_month_label(cal_yr1, cal_m1)}"
        cal_pts   = _pts_label(len(cal_data["x"]))
        # Second Period occurrence is Callao
        html = re.sub(
            r"(Period:\s*<strong>)([^<]+)(</strong>)",
            lambda m: m.group(1) + cal_range + m.group(3),
            html,
            count=1,
        )
        # Second Points occurrence is Callao
        html = re.sub(
            r"(Points:\s*<strong>)([\d,]+)(</strong>)",
            lambda m: m.group(1) + cal_pts + m.group(3),
            html,
            count=1,
        )

    # ── Header subtitle date range ────────────────────────────────────────────
    if obs_data is not None:
        # "NINO1+2 SST 1975–2026" → update the year range
        html = re.sub(
            r"(NINO1\+2 SST )(\d{4}–\d{4})",
            lambda m: m.group(1) + f"{sst_yr0}–{sst_yr1}",
            html,
        )
        # "Callao SL 1970–2026" → update if cal_data exists
    if cal_data is not None:
        html = re.sub(
            r"(Callao SL )(\d{4}–\d{4})",
            lambda m: m.group(1) + f"{cal_yr0}–{cal_yr1}",
            html,
        )

    return html


def _find_sst_dat(out_dir: Path, hn1: int, hn2: int) -> Path | None:
    """Glob for the SST output file (date range in filename)."""
    pattern = str(out_dir / f"sva.2_filter_{hn1}_{hn2}_*_SAIDApy.dat")
    matches = sorted(glob.glob(pattern))
    return Path(matches[-1]) if matches else None


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
# Pipeline runners (mirrors run_all.py but returns the .dat path)
# ---------------------------------------------------------------------------

def _run_sst_pipeline(cfg: dict, hn1: float, hn2: float, ndots: int,
                      out_dir: Path) -> tuple[Path, dict]:
    """Download SST, filter, write .dat. Returns (dat_path, result_dict)."""
    yr0 = int(cfg["sst"]["ano_inicio"])
    tmp_path = out_dir / f"sva.2_filter_{int(hn1)}_{int(hn2)}_SAIDApy_update_tmp.dat"

    result = pipeline.run_sst(
        local_file=cfg["sst"]["local_file"],
        ano_inicio=yr0,
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(tmp_path),
    )

    yr1 = int(result["IYR"][-1])
    m0  = int(result["MES"][0])
    m1  = int(result["MES"][-1])
    final = out_dir / f"sva.2_filter_{int(hn1)}_{int(hn2)}_{yr0}.{m0}_{yr1}.{m1}_SAIDApy.dat"
    tmp_path.rename(final)
    result["output_file"] = str(final)
    return final, result


def _run_sl_pipeline(st: dict, hn1: float, hn2: float, ndots: int,
                     out_dir: Path) -> tuple[Path, dict]:
    """Download sea level for one station, filter, write .dat."""
    dat = out_dir / f"sva.2_filter_{st['name']}_SAIDApy.dat"
    result = pipeline.run_sea_level(
        station_id=st["id"],
        station_name=st["name"],
        start_date=st["start_date"],
        HN1=hn1, HN2=hn2, NDOTS=ndots,
        output_file=str(dat),
    )
    return dat, result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="update_website.py",
        description="Refresh ENSO data and re-embed JS arrays in docs/index.html.",
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
        help="Update only the SST (NINO1+2) array; skip Callao sea level",
    )
    parser.add_argument(
        "--no-push", action="store_true",
        help="Update docs/index.html but skip the git add/commit/push step",
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
            f"This file contains NINO1+2 SST 1950–1981 and must be present.\n"
            f"In CI/CD it lives at assets/data/sst1950_1981.txt and is copied\n"
            f"to data/input/ by the workflow before running this script.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if not INDEX_HTML.exists():
        print(f"ERROR: {INDEX_HTML} not found", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    hn1   = float(cfg["filter"]["HN1"])
    hn2   = float(cfg["filter"]["HN2"])
    ndots = int(cfg["filter"]["NDOTS"])

    t0 = time.time()

    # ── SST pipeline ──────────────────────────────────────────────────────────
    print("[1] SST pipeline (NINO1+2) …")

    # Record old point count for the diff summary
    old_sst_path = _find_sst_dat(OUT_DIR, int(hn1), int(hn2))
    old_sst_n    = _count_monthly(old_sst_path) if old_sst_path else 0

    sst_dat, sst_result = _run_sst_pipeline(cfg, hn1, hn2, ndots, OUT_DIR)
    sst_data = _load_dat(str(sst_dat))

    sst_yr0 = int(sst_result["IYR"][0]);  sst_m0 = int(sst_result["MES"][0])
    sst_yr1 = int(sst_result["IYR"][-1]); sst_m1 = int(sst_result["MES"][-1])
    new_sst_n = sum(1 for v in sst_data["irest"] if v == 0)
    delta_sst = new_sst_n - old_sst_n

    print(
        f"  SST:    {_month_label(sst_yr0,sst_m0)} – {_month_label(sst_yr1,sst_m1)}"
        f"  ({new_sst_n} months, {delta_sst:+d} new)"
    )

    # ── Callao pipeline ───────────────────────────────────────────────────────
    cal_data = None
    cal_yr0 = cal_m0 = cal_yr1 = cal_m1 = 0

    if not args.sst_only:
        print("[2] Callao sea level pipeline …")
        callao_cfg = cfg["stations"]["callao"]

        cal_dat_path = OUT_DIR / f"sva.2_filter_{callao_cfg['name']}_SAIDApy.dat"
        old_cal_n    = _count_monthly(cal_dat_path) if cal_dat_path.exists() else 0

        cal_dat, cal_result = _run_sl_pipeline(callao_cfg, hn1, hn2, ndots, OUT_DIR)
        cal_data = _load_dat(str(cal_dat))

        cal_yr0 = int(cal_result["IYR"][0]);  cal_m0 = int(cal_result["MES"][0])
        cal_yr1 = int(cal_result["IYR"][-1]); cal_m1 = int(cal_result["MES"][-1])
        new_cal_n = sum(1 for v in cal_data["irest"] if v == 0)
        delta_cal = new_cal_n - old_cal_n

        print(
            f"  Callao: {_month_label(cal_yr0,cal_m0)} – {_month_label(cal_yr1,cal_m1)}"
            f"  ({new_cal_n} months, {delta_cal:+d} new)"
        )

    # ── Patch HTML ────────────────────────────────────────────────────────────
    print(f"[{'3' if not args.sst_only else '2'}] Patching {INDEX_HTML} …")

    html = INDEX_HTML.read_text(encoding="utf-8")
    new_html = _patch_html(
        html,
        obs_data=sst_data,
        cal_data=cal_data,
        sst_yr0=sst_yr0, sst_m0=sst_m0, sst_yr1=sst_yr1, sst_m1=sst_m1,
        cal_yr0=cal_yr0, cal_m0=cal_m0, cal_yr1=cal_yr1, cal_m1=cal_m1,
    )

    if args.dry_run:
        obs_n   = len(sst_data["x"])
        cal_n   = len(cal_data["x"]) if cal_data else 0
        print(f"  [dry-run] Would write {obs_n} SST points + {cal_n} Callao points")
        print(f"  [dry-run] No files written.")
    else:
        INDEX_HTML.write_text(new_html, encoding="utf-8")
        print(f"  Written: {INDEX_HTML}")

    # ── Git push ──────────────────────────────────────────────────────────────
    if not args.dry_run and not args.no_push:
        print("[4] Committing and pushing …")
        month_str = f"{sst_yr1}-{sst_m1:02d}"
        msg = f"data: update ENSO arrays through {month_str} [auto]"
        cmds = [
            ["git", "add", str(INDEX_HTML)],
            ["git", "commit", "-m", msg],
            ["git", "push"],
        ]
        for cmd in cmds:
            result_p = subprocess.run(cmd, capture_output=True, text=True)
            if result_p.returncode != 0:
                print(f"  WARNING: {' '.join(cmd)} exited {result_p.returncode}")
                print(f"  stderr: {result_p.stderr.strip()}")
                break
            print(f"  OK: {' '.join(cmd)}")

    print(f"\nDone in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
