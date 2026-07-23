"""
el_nino.plots
=============
Phase-diagram visualisations: static figures, time-series, and animations.

Each animation frame shows three layers:
  - Gray line : historical trajectory before the rolling latest year
  - Red line  : rolling latest 12 calendar months, with monthly markers
  - Gold dot  : current position in phase space

The time label in the top-left corner shows "YYYY MM" so the viewer can
read El Niño events as the trajectory evolves.

All functions accept a ``data`` dict produced by ``pipeline.load_output``
with keys: T, dT, year, month, irest.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

from el_nino import pipeline


RECENT_WINDOW_MONTHS = 12

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _prepare_xy(data: dict, remove_mean: bool) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract plotting arrays from a load_output dict.

    For sea level data the caller passes remove_mean=True so the x-axis
    shows anomaly (centred at zero) rather than absolute level.  For SST
    we leave the absolute temperature unchanged (remove_mean=False).
    """
    x = data["T"].copy()
    if remove_mean:
        x -= float(np.nanmean(x))
    y = data["dT"].copy()
    return x, y


def _recent_window_start_index(
    year: np.ndarray,
    month: np.ndarray,
    window_months: int = RECENT_WINDOW_MONTHS,
) -> int:
    """Return the first sample in the rolling calendar-month window."""
    if window_months < 1:
        raise ValueError("window_months must be at least 1")
    if len(year) == 0 or len(year) != len(month):
        raise ValueError("year and month must be non-empty arrays of equal length")
    ym = np.asarray(year, dtype=np.int64) * 12 + np.asarray(month, dtype=np.int64)
    if np.any(np.diff(ym) < 0):
        raise ValueError("phase-diagram dates must be chronological")
    first_recent = int(ym[-1]) - (window_months - 1)
    return int(np.searchsorted(ym, first_recent, side="left"))


def _setup_axes(
    ax: plt.Axes,
    title: str,
    xlabel: str,
    xlim: list,
    ylim: list,
) -> None:
    """Apply common axis formatting shared by all four functions."""
    ax.set_title(title, fontsize=13)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("dT/dt")
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.7)
    # Reference lines at x=0 and y=0 mark the sign-change boundaries of
    # T and its rate of change — crucial landmarks for reading the ENSO phase.
    ax.axvline(0.0, linestyle="--", linewidth=1.0, color="black", alpha=0.8)
    ax.axhline(0.0, linestyle="--", linewidth=1.0, color="black", alpha=0.8)


# ---------------------------------------------------------------------------
# Function 1 — Static phase diagram
# ---------------------------------------------------------------------------

def plot_phase_diagram(
    data: dict,
    title: str,
    xlabel: str,
    xlim: list,
    ylim: list,
    save_path: str | None = None,
    remove_mean: bool = False,
) -> matplotlib.figure.Figure:
    """
    Static phase diagram with subdued history, the rolling latest 12
    calendar months in red, monthly markers, and a larger gold endpoint.

    Parameters
    ----------
    data        : dict from pipeline.load_output() — keys T, dT, year, month, irest
    title       : str — figure title
    xlabel      : str — x-axis label (e.g. "Temperature (°C)")
    xlim        : list [xmin, xmax]
    ylim        : list [ymin, ymax]
    save_path   : str or None — if given, save figure to this path
    remove_mean : bool — if True, subtract mean(T) from T before plotting

    Returns
    -------
    matplotlib.figure.Figure
    """
    x, y = _prepare_xy(data, remove_mean)
    year = np.asarray(data["year"])
    month = np.asarray(data["month"])
    irest = np.asarray(data["irest"])
    recent_start = _recent_window_start_index(year, month)

    fig, ax = plt.subplots(figsize=(8, 6))
    _setup_axes(ax, title, xlabel, xlim, ylim)

    if recent_start > 0:
        ax.plot(
            x[: recent_start + 1],
            y[: recent_start + 1],
            color="#777777",
            linewidth=1.2,
            alpha=0.75,
            label="Historical",
        )
    ax.plot(
        x[recent_start:],
        y[recent_start:],
        color="#dc2626",
        linewidth=2.2,
        alpha=0.95,
        label="Latest 12 months",
    )
    monthly = np.arange(len(x))[(np.arange(len(x)) >= recent_start) & (irest == 0)]
    ax.scatter(
        x[monthly],
        y[monthly],
        s=20,
        color="#dc2626",
        edgecolor="white",
        linewidth=0.7,
        zorder=4,
    )
    ax.plot(
        [x[-1]],
        [y[-1]],
        marker="o",
        linestyle="none",
        markersize=9,
        markerfacecolor="#ffbf00",
        markeredgecolor="#7a4f00",
        markeredgewidth=1.1,
        color="#ffbf00",
        label="Current",
        zorder=5,
    )
    ax.legend(loc="best")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


# ---------------------------------------------------------------------------
# Function 2 — Animated phase diagram
# ---------------------------------------------------------------------------

def animate_phase_diagram(
    data: dict,
    title: str,
    xlabel: str,
    xlim: list,
    ylim: list,
    tail_months: int = 12,
    save_path: str | None = None,
    fps: int = 15,
    dpi: int = 150,
    remove_mean: bool = False,
) -> animation.FuncAnimation:
    """
    Animated phase diagram: the rotating-attractor animation.

    Three overlaid layers update every frame:
    - Gray line  : historical trajectory before the rolling window
    - Red line   : rolling latest ``tail_months`` calendar months
    - Red dots   : monthly samples inside that window
    - Gold dot   : current position

    Parameters
    ----------
    data        : dict from pipeline.load_output()
    title       : str — figure title
    xlabel      : str — x-axis label
    xlim        : list [xmin, xmax]
    ylim        : list [ymin, ymax]
    tail_months : int — calendar months shown in red (default 12)
    save_path   : str or None — if given, save as .mp4 via ffmpeg
    fps         : int — frames per second (default 15)
    dpi         : int — resolution (default 150)
    remove_mean : bool — if True, subtract mean(T) from T before plotting

    Returns
    -------
    matplotlib.animation.FuncAnimation
    """
    x, y  = _prepare_xy(data, remove_mean)
    year = np.asarray(data["year"])
    month = np.asarray(data["month"])
    irest = np.asarray(data["irest"])

    if tail_months < 1:
        raise ValueError("tail_months must be at least 1")
    ym = np.asarray(year, dtype=np.int64) * 12 + np.asarray(month, dtype=np.int64)
    _recent_window_start_index(year, month, tail_months)

    sample_path = np.column_stack([x, y])
    N = len(x)

    fig, ax = plt.subplots(figsize=(8, 6))
    _setup_axes(ax, title, xlabel, xlim, ylim)

    # Artists declared here so the closure captures every visual layer.
    line_full, = ax.plot([], [], color="#777777", linewidth=1.2, alpha=0.75)
    line_tail, = ax.plot([], [], color="#dc2626", linewidth=2.2, alpha=0.95)
    dots_monthly, = ax.plot(
        [], [], "o", markersize=3.5, color="#dc2626",
        markeredgecolor="white", markeredgewidth=0.6,
    )
    dot_curr, = ax.plot(
        [], [], "o", markersize=9, color="#ffbf00",
        markeredgecolor="#7a4f00", markeredgewidth=1.1,
    )

    # Time label in axes coordinates so it never clips against data limits.
    time_text = ax.text(
        0.02, 0.95, "",
        transform=ax.transAxes,
        fontsize=13, va="top",
    )

    def _init():
        line_full.set_data([], [])
        line_tail.set_data([], [])
        dots_monthly.set_data([], [])
        dot_curr.set_data([], [])
        time_text.set_text("")
        return line_full, line_tail, dots_monthly, dot_curr, time_text

    def _update(num: int):
        first_recent_ym = int(ym[num]) - (tail_months - 1)
        start = int(np.searchsorted(ym[: num + 1], first_recent_ym, side="left"))

        # History stops where the red rolling-year trajectory begins.
        line_full.set_data(x[: start + 1], y[: start + 1])

        # Red tail: slides a fixed-length window behind the current point.
        line_tail.set_data(
            sample_path[start : num + 1, 0],
            sample_path[start : num + 1, 1],
        )

        monthly = np.arange(start, num + 1)[irest[start : num + 1] == 0]
        dots_monthly.set_data(x[monthly], y[monthly])

        # Gold dot at current position.
        dot_curr.set_data([x[num]], [y[num]])

        # "YYYY MM" label matches the notebook convention.
        time_text.set_text(f"{int(year[num]):04d} {int(month[num]):02d}")

        return line_full, line_tail, dots_monthly, dot_curr, time_text

    ani = animation.FuncAnimation(
        fig,
        _update,
        frames=N,
        init_func=_init,
        interval=int(1000 / fps),
        blit=True,
        repeat=False,
    )

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        ani.save(save_path, writer="ffmpeg", fps=fps, dpi=dpi)

    return ani


# ---------------------------------------------------------------------------
# Function 3 — Time series
# ---------------------------------------------------------------------------

def plot_timeseries(
    data: dict,
    title: str,
    ylabel: str,
    save_path: str | None = None,
) -> matplotlib.figure.Figure:
    """
    Simple time series of T and dT/dt against time.

    Only monthly points (irest == 0) are plotted — sub-monthly
    interpolated points would make the line too dense to read.
    dT/dt is shown on a twin y-axis so both signals share the same
    time axis without axis-scaling conflicts.

    Parameters
    ----------
    data      : dict from pipeline.load_output()
    title     : str — figure title
    ylabel    : str — left y-axis label for T
    save_path : str or None — if given, save figure to this path

    Returns
    -------
    matplotlib.figure.Figure
    """
    # Restrict to original monthly grid points for readability.
    mask  = data["irest"] == 0
    T     = data["T"][mask]
    dT    = data["dT"][mask]
    year  = data["year"][mask]
    month = data["month"][mask]

    # Fractional-year x-axis: Jan 1975 → 1975.0, Feb 1975 → 1975.083, …
    t = year + (month - 1) / 12.0

    fig, ax1 = plt.subplots(figsize=(12, 4))
    ax1.set_title(title, fontsize=13)
    ax1.set_xlabel("Year")
    ax1.set_ylabel(ylabel, color="steelblue")
    ax1.plot(t, T, color="steelblue", linewidth=1.2)
    ax1.tick_params(axis="y", labelcolor="steelblue")
    ax1.axhline(0.0, linestyle="--", linewidth=0.8, color="steelblue", alpha=0.4)
    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)

    # Twin axis: share the time axis, separate y scale for derivative.
    ax2 = ax1.twinx()
    ax2.set_ylabel("dT/dt", color="firebrick")
    ax2.plot(t, dT, color="firebrick", linewidth=0.9, alpha=0.8)
    ax2.tick_params(axis="y", labelcolor="firebrick")
    ax2.axhline(0.0, linestyle="--", linewidth=0.8, color="firebrick", alpha=0.4)

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


# ---------------------------------------------------------------------------
# Function 4 — Convenience wrapper for all four datasets
# ---------------------------------------------------------------------------

def animate_all_from_config(config_path: str = "config.yaml") -> None:
    """
    Create and save all four phase-diagram animations from config.yaml.

    Assumes the .dat output files already exist (produced by
    ``pipeline.run_all``).  The SST file is located by globbing for the
    filter-parameter pattern; sea level filenames are constructed from
    the station name in config.yaml.

    SST        → remove_mean=False (absolute temperature, °C)
    Sea level  → remove_mean=True  (anomaly relative to the record mean)

    Animations are saved to data/output/ with names of the form::

        animation_SST_filter_10_9.mp4
        animation_Callao_filter_10_9.mp4
        …

    Parameters
    ----------
    config_path : str — path to config.yaml (default: "config.yaml")
    """
    import glob
    import yaml

    with open(config_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    flt     = cfg["filter"]
    HN1     = int(flt["HN1"])
    HN2     = int(flt["HN2"])
    out_dir = Path("data/output")

    # --- SST ---
    # The SST filename includes the actual data date range, which is only
    # known after downloading.  We glob for any file matching the filter
    # parameters and pick the newest if multiple runs exist.
    sst_pattern = str(out_dir / f"sva.2_filter_{HN1}_{HN2}_*_SAIDApy.dat")
    sst_files   = glob.glob(sst_pattern)
    if not sst_files:
        raise FileNotFoundError(
            f"No SST output file found matching: {sst_pattern}\n"
            "Run pipeline.run_all() first to generate the .dat files."
        )
    sst_file = sorted(sst_files)[-1]
    print(f"Animating SST ({Path(sst_file).name}) …")
    sst_data      = pipeline.load_output(sst_file)
    sst_anim_path = str(out_dir / f"animation_SST_filter_{HN1}_{HN2}.mp4")
    animate_phase_diagram(
        data=sst_data,
        title=f"El Niño SST — Fourier filter [{HN1}, {HN2}] months",
        xlabel="Temperature (°C)",
        xlim=[17.5, 32.5],
        ylim=[-2.5, 2.5],
        remove_mean=False,
        save_path=sst_anim_path,
    )
    print(f"  Saved: {sst_anim_path}")

    # --- Sea level stations ---
    for key, st in cfg["stations"].items():
        name     = st["name"]
        sl_file  = str(out_dir / f"sva.2_filter_{name}_SAIDApy.dat")
        anim_out = str(out_dir / f"animation_{name}_filter_{HN1}_{HN2}.mp4")
        print(f"Animating {name} ({Path(sl_file).name}) …")
        sl_data = pipeline.load_output(sl_file)
        animate_phase_diagram(
            data=sl_data,
            title=f"Sea Level — {name}",
            xlabel="Sea level anomaly (cm)",
            xlim=st["xlim"],
            ylim=st["ylim"],
            remove_mean=True,
            save_path=anim_out,
        )
        print(f"  Saved: {anim_out}")


# ---------------------------------------------------------------------------
# Self-test (no network, no file I/O, no display)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Verify that all three plot functions run without error on synthetic data.

    Uses the Agg (non-interactive) backend so the test passes in headless
    environments (CI, remote servers) without a display.
    """
    # Switch to non-interactive backend before any figure is created.
    # plt.switch_backend avoids the UserWarning that matplotlib.use() raises
    # when called after pyplot has already been imported.
    plt.switch_backend("Agg")

    print("Running self-test …")

    # Build synthetic data mimicking a 120-month run with NDOTS=5 (596 points).
    NT    = 120
    NDOTS = 5
    NTD   = (NT - 1) * NDOTS + 1   # 596

    t_monthly = np.arange(NT, dtype=float)
    T_monthly = (
        25.0
        + 2.0 * np.sin(2.0 * np.pi * t_monthly / 12.0)
        + 0.5 * np.sin(2.0 * np.pi * t_monthly / 36.0)
    )

    # Fine-grid arrays: interpolate T linearly between monthly points
    # (just for testing purposes — not the actual Fourier interpolation).
    t_fine = np.linspace(0, NT - 1, NTD)
    T_fine = np.interp(t_fine, t_monthly, T_monthly)
    dT_fine = np.gradient(T_fine)

    # IREST cycles 0, 1, 2, 3, 4, 0, 1, … across NTD points.
    irest_arr = np.tile(np.arange(NDOTS), NT)[: NTD]

    # Year and month arrays: broadcast monthly values to fine grid.
    year_monthly  = 1975 + t_monthly.astype(int) // 12
    month_monthly = (t_monthly.astype(int) % 12) + 1
    year_fine  = np.repeat(year_monthly,  NDOTS)[: NTD]
    month_fine = np.repeat(month_monthly, NDOTS)[: NTD]

    data = {
        "T":     T_fine,
        "dT":    dT_fine,
        "year":  year_fine.astype(np.int32),
        "month": month_fine.astype(np.int32),
        "irest": irest_arr.astype(np.int32),
    }

    # --- Test 1: plot_phase_diagram returns a Figure ---
    fig = plot_phase_diagram(
        data=data,
        title="Self-test SST",
        xlabel="Temperature (°C)",
        xlim=[17.5, 32.5],
        ylim=[-2.5, 2.5],
    )
    assert isinstance(fig, matplotlib.figure.Figure), (
        f"FAIL 1: plot_phase_diagram returned {type(fig)}"
    )
    plt.close(fig)
    print("  PASS 1: plot_phase_diagram returns a Figure")

    # --- Test 2: plot_phase_diagram with remove_mean=True ---
    fig2 = plot_phase_diagram(
        data=data,
        title="Self-test SL anomaly",
        xlabel="Sea level anomaly (cm)",
        xlim=[-300, 300],
        ylim=[-60, 60],
        remove_mean=True,
    )
    assert isinstance(fig2, matplotlib.figure.Figure), (
        f"FAIL 2: plot_phase_diagram (remove_mean=True) returned {type(fig2)}"
    )
    plt.close(fig2)
    print("  PASS 2: plot_phase_diagram with remove_mean=True returns a Figure")

    # --- Test 3: animate_phase_diagram returns a FuncAnimation ---
    ani = animate_phase_diagram(
        data=data,
        title="Self-test animation",
        xlabel="Temperature (°C)",
        xlim=[17.5, 32.5],
        ylim=[-2.5, 2.5],
        save_path=None,   # no file I/O
    )
    assert isinstance(ani, animation.FuncAnimation), (
        f"FAIL 3: animate_phase_diagram returned {type(ani)}"
    )
    plt.close("all")
    print("  PASS 3: animate_phase_diagram returns a FuncAnimation")

    # --- Test 4: plot_timeseries returns a Figure ---
    fig3 = plot_timeseries(
        data=data,
        title="Self-test time series",
        ylabel="Temperature (°C)",
    )
    assert isinstance(fig3, matplotlib.figure.Figure), (
        f"FAIL 4: plot_timeseries returned {type(fig3)}"
    )
    plt.close(fig3)
    print("  PASS 4: plot_timeseries returns a Figure")

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
