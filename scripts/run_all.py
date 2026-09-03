"""
scripts/run_all.py
==================
Main entry point: download all 4 datasets, run the Fourier filter
pipeline, and save static phase diagrams, animated attractors, and
time series plots.

Run from the project root directory:

    python scripts/run_all.py                     # all 4 datasets
    python scripts/run_all.py --sst-only          # only NINO1+2 SST
    python scripts/run_all.py --no-animate        # skip MP4 (faster)
    python scripts/run_all.py --config path.yaml  # custom config file
"""

import argparse
import sys
import time
from pathlib import Path

import matplotlib
# Set non-interactive backend before any pyplot import.  plots.py imports
# pyplot at module level, so this must happen before that import is executed.
matplotlib.use("Agg")

import yaml

from el_nino import pipeline
from el_nino.plots import (
    animate_phase_diagram,
    plot_phase_diagram,
    plot_timeseries,
)


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

def _check_sst_file(local_file: str) -> None:
    """
    Exit with a clear message if the historical SST file is missing.

    The pre-1982 NINO1+2 record is not available from the NOAA CPC online
    endpoint, so it must be supplied as a local file before running the
    pipeline.
    """
    if not Path(local_file).exists():
        print(
            f"\nERROR: Historical SST file not found at:\n"
            f"  {Path(local_file).resolve()}\n\n"
            f"This file contains the NINO1+2 SST record from 1950 to 1981.\n"
            f"Data from 1982 onward is downloaded automatically from NOAA CPC.\n\n"
            f"To fix:\n"
            f"  1. Obtain the file from the research group or project archive.\n"
            f"  2. Copy it to:  {Path(local_file).resolve()}\n"
            f"  3. Expected format — 10 whitespace-delimited columns, one header line:\n"
            f"       YR  MON  NINO12  ANOM12  NINO3  ANOM3  NINO4  ANOM4  NINO34  ANOM34\n",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Per-dataset pipeline runners (mirror pipeline.run_all internals)
# ---------------------------------------------------------------------------

def _run_sst(cfg: dict, HN1: float, HN2: float, NDOTS: int,
             out_dir: Path) -> dict:
    """
    Run the SST pipeline and rename the output file to the date-range
    convention used by the reference Fortran program.

    Mirrors the rename logic inside pipeline.run_all so that the output
    filenames are consistent regardless of which entry point is used.
    """
    yr0 = int(cfg["sst"]["ano_inicio"])
    tmp = out_dir / f"sva.2_filter_{int(HN1)}_{int(HN2)}_SAIDApy_tmp.dat"

    result = pipeline.run_sst(
        local_file=cfg["sst"]["local_file"],
        ano_inicio=yr0,
        HN1=HN1, HN2=HN2, NDOTS=NDOTS,
        output_file=str(tmp),
    )

    # Rename once we know the actual start/end dates of the downloaded series.
    yr1    = int(result["IYR"][-1])
    m0     = int(result["MES"][0])
    m1     = int(result["MES"][-1])
    final  = (
        out_dir
        / f"sva.2_filter_{int(HN1)}_{int(HN2)}"
          f"_{yr0}.{m0}_{yr1}.{m1}_SAIDApy.dat"
    )
    tmp.rename(final)
    result["output_file"] = str(final)
    print(f"  Renamed → {final.name}")
    return result


def _run_sea_level(st: dict, HN1: float, HN2: float, NDOTS: int,
                   out_dir: Path) -> dict:
    """Run the sea level pipeline for one station."""
    dat = out_dir / f"sva.2_filter_{st['name']}_SAIDApy.dat"
    return pipeline.run_sea_level(
        station_id=st["id"],
        station_name=st["name"],
        start_date=st["start_date"],
        HN1=HN1, HN2=HN2, NDOTS=NDOTS,
        output_file=str(dat),
        rqd_url=st.get("rqd_url"),
    )


# ---------------------------------------------------------------------------
# Plot generation
# ---------------------------------------------------------------------------

def _make_plots(
    name: str,
    result: dict,
    title_prefix: str,
    xlabel: str,
    xlim: list,
    ylim: list,
    out_dir: Path,
    animate: bool,
    remove_mean: bool,
    units: str,
) -> list[str]:
    """
    Generate the three standard outputs for one dataset:
      1. Static phase diagram (PNG)
      2. Animated attractor (MP4) — skipped when animate=False
      3. Time series (PNG)

    Returns a list of paths of files written.
    """
    import matplotlib.pyplot as plt

    data = pipeline.load_output(result["output_file"])
    safe  = name.replace(" ", "_")
    written: list[str] = []

    # 1. Static phase diagram
    phase_path = str(out_dir / f"phase_diagram_{safe}.png")
    fig = plot_phase_diagram(
        data=data,
        title=f"{title_prefix} — Phase Diagram",
        xlabel=xlabel,
        xlim=xlim,
        ylim=ylim,
        remove_mean=remove_mean,
        save_path=phase_path,
    )
    plt.close(fig)
    written.append(phase_path)
    print(f"    phase diagram  → {phase_path}")

    # 2. Animated attractor
    if animate:
        anim_path = str(out_dir / f"animation_{safe}.mp4")
        ani = animate_phase_diagram(
            data=data,
            title=f"{title_prefix} — Attractor",
            xlabel=xlabel,
            xlim=xlim,
            ylim=ylim,
            remove_mean=remove_mean,
            fps=15,
            dpi=150,
            save_path=anim_path,
        )
        plt.close("all")
        written.append(anim_path)
        print(f"    animation      → {anim_path}")

    # 3. Time series
    ylabel = f"{xlabel.split('(')[0].strip()} ({units})"
    ts_path = str(out_dir / f"timeseries_{safe}.png")
    fig = plot_timeseries(
        data=data,
        title=f"{title_prefix} — Time Series",
        ylabel=ylabel,
        save_path=ts_path,
    )
    plt.close(fig)
    written.append(ts_path)
    print(f"    time series    → {ts_path}")

    return written


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _fmt_date(iyr: int, mes: int) -> str:
    return f"{int(iyr):04d}/{int(mes):02d}"


def _print_summary(rows: list[dict]) -> None:
    """Print a formatted summary table and per-dataset file lists."""
    col_widths = [16, 22, 6, 9, 9]
    headers    = ["Dataset", "Date range", "NT", "SIGMA30", "SIGMA04"]
    sep        = "  "

    def _fmt_row(cells: list[str]) -> str:
        return sep.join(f"{c:<{w}}" for c, w in zip(cells, col_widths))

    bar = "=" * 72
    print()
    print(bar)
    print("  SUMMARY")
    print(bar)
    print(_fmt_row(headers))
    print("-" * 72)
    for r in rows:
        print(_fmt_row([
            r["name"],
            r["date_range"],
            str(r["NT"]),
            f"{r['sigma30']:.4f}",
            f"{r['sigma04']:.4f}",
        ]))
    print(bar)

    print()
    print("Output files:")
    for r in rows:
        print(f"  {r['name']}:")
        for f in r["files"]:
            print(f"    {f}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run_all.py",
        description=(
            "Download El Niño data, apply the Fourier filter, "
            "and save phase diagrams and animations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python scripts/run_all.py\n"
            "  python scripts/run_all.py --sst-only\n"
            "  python scripts/run_all.py --no-animate\n"
            "  python scripts/run_all.py --config myconfig.yaml\n"
        ),
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--sst-only", action="store_true",
        help="Run only the SST pipeline; skip sea level stations",
    )
    parser.add_argument(
        "--no-animate", action="store_true",
        help="Skip MP4 animation generation (produces PNGs only, much faster)",
    )
    args = parser.parse_args()

    # ── Config ───────────────────────────────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    HN1   = float(cfg["filter"]["HN1"])
    HN2   = float(cfg["filter"]["HN2"])
    NDOTS = int(cfg["filter"]["NDOTS"])
    animate = not args.no_animate

    # ── Pre-flight ────────────────────────────────────────────────────────────
    _check_sst_file(cfg["sst"]["local_file"])

    # Station list respects --sst-only
    station_items = [] if args.sst_only else list(cfg["stations"].items())
    total = 1 + len(station_items)

    summary_rows: list[dict] = []
    t0_all = time.time()

    # ── [1/N] SST ─────────────────────────────────────────────────────────────
    print(f"\n[1/{total}] SST pipeline (NINO1+2) …")
    t0 = time.time()

    sst_result = _run_sst(cfg, HN1, HN2, NDOTS, out_dir)

    print("  Generating plots …")
    sst_files = _make_plots(
        name="SST",
        result=sst_result,
        title_prefix=f"NINO1+2 SST  [filter {int(HN1)}/{int(HN2)} months]",
        xlabel="Temperature (°C)",
        xlim=[17.5, 32.5],
        ylim=[-2.5, 2.5],
        out_dir=out_dir,
        animate=animate,
        remove_mean=False,
        units="°C",
    )
    print(f"  Done in {time.time() - t0:.1f}s")

    summary_rows.append({
        "name":       "SST (NINO1+2)",
        "date_range": (
            f"{_fmt_date(sst_result['IYR'][0],  sst_result['MES'][0])} → "
            f"{_fmt_date(sst_result['IYR'][-1], sst_result['MES'][-1])}"
        ),
        "NT":      len(sst_result["IYR"]),
        "sigma30": sst_result["sigma30"],
        "sigma04": sst_result["sigma04"],
        "files":   [sst_result["output_file"]] + sst_files,
    })

    # ── [2..N] Sea level ──────────────────────────────────────────────────────
    for step, (key, st) in enumerate(station_items, start=2):
        name = st["name"]
        print(f"\n[{step}/{total}] {name} sea level (UHSLC {st['id']}) …")
        t0 = time.time()

        sl_result = _run_sea_level(st, HN1, HN2, NDOTS, out_dir)

        print("  Generating plots …")
        sl_files = _make_plots(
            name=name,
            result=sl_result,
            title_prefix=f"{name} Sea Level  [filter {int(HN1)}/{int(HN2)} months]",
            xlabel="Sea level anomaly (mm)",
            xlim=st["xlim"],
            ylim=st["ylim"],
            out_dir=out_dir,
            animate=animate,
            remove_mean=True,
            units="mm",
        )
        print(f"  Done in {time.time() - t0:.1f}s")

        summary_rows.append({
            "name":       name,
            "date_range": (
                f"{_fmt_date(sl_result['IYR'][0],  sl_result['MES'][0])} → "
                f"{_fmt_date(sl_result['IYR'][-1], sl_result['MES'][-1])}"
            ),
            "NT":      len(sl_result["IYR"]),
            "sigma30": sl_result["sigma30"],
            "sigma04": sl_result["sigma04"],
            "files":   [sl_result["output_file"]] + sl_files,
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    _print_summary(summary_rows)
    print(f"Total elapsed: {time.time() - t0_all:.1f}s")


if __name__ == "__main__":
    main()
