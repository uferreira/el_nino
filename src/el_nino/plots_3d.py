"""
el_nino.plots_3d
================
3D phase-diagram visualisations in the extended phase space
(T, dT/dt, z) where z is one of:

  "accel"  — d²T/dt², the second time derivative of the observable.
             This embeds the attractor in the full (T, T', T'') space,
             revealing whether the dynamics are locally accelerating or
             decelerating.  Corresponds exactly to the AST array produced
             by deri_fourier.

  "phase"  — Annual forcing phase θ = 2π·(month-1+irest/NDOTS)/12 mod 2π.
             This wraps the 2D phase diagram onto a cylinder (the Poincaré
             cylinder of the periodically forced oscillator), separating the
             El Niño and La Niña seasons along the z-axis.

Functions
---------
compute_z               — compute the z-axis array for a chosen mode
plot_phase_diagram_3d   — static 3D figure with optional Duffing overlay
animate_phase_diagram_3d — animated 3D figure
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize
from mpl_toolkits.mplot3d.art3d import Line3DCollection

from el_nino.plots import _prepare_xy


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_z(
    data: dict,
    mode: str = "accel",
    z_array: np.ndarray | None = None,
) -> np.ndarray:
    """
    Compute the z-axis array for 3D phase diagrams.

    Parameters
    ----------
    data    : dict from pipeline.load_output() — keys: T, dT, year, month, irest
    mode    : "accel" or "phase"
    z_array : pre-computed d²T/dt² of shape (NTD,); used only for mode="accel".
              If None and mode="accel", falls back to np.gradient of dT.

    Returns
    -------
    z : float64 array of length NTD = len(data["T"])

    Raises
    ------
    ValueError
        If mode is not "accel" or "phase".
    """
    if mode == "accel":
        if z_array is not None:
            return np.asarray(z_array, dtype=np.float64)
        # Fallback: numerical second derivative via gradient of dT/dt.
        NDOTS = int(data["irest"].max()) + 1
        return np.gradient(data["dT"], 1.0 / NDOTS)

    elif mode == "phase":
        # Annual forcing phase: theta in [0, 2π), cycling once per year.
        # month 1, irest=0 → 0 rad; month 7, irest=0 → π rad.
        NDOTS = int(data["irest"].max()) + 1
        month = data["month"].astype(np.float64)
        irest = data["irest"].astype(np.float64)
        phi   = (
            2.0 * np.pi * ((month - 1.0 + irest / NDOTS) / 12.0) % (2.0 * np.pi)
        )
        return phi

    else:
        raise ValueError(f"Unknown mode {mode!r}. Expected 'accel' or 'phase'.")


def plot_phase_diagram_3d(
    data: dict,
    title: str,
    xlabel: str,
    z_array: np.ndarray,
    zlabel: str,
    save_path: str | None = None,
    remove_mean: bool = False,
    duffing_xyz: tuple | None = None,
) -> matplotlib.figure.Figure:
    """
    Static 3D phase diagram with a time-ordered blue-to-red colour gradient.

    The colour gradient is implemented via a Line3DCollection of N-1
    segments, each coloured by its position in the time series, giving a
    perceptually uniform time-encoding without a separate legend.

    Parameters
    ----------
    data        : dict from pipeline.load_output()
    title       : figure title
    xlabel      : x-axis label (e.g. "Temperature (°C)")
    z_array     : pre-computed z values of shape (NTD,)
    zlabel      : z-axis label (e.g. "d²T/dt²" or "Annual phase (rad)")
    save_path   : if given, save PNG to this path (parent created if absent)
    remove_mean : if True, subtract mean(T) from T before plotting
    duffing_xyz : optional tuple (x_arr, y_arr, z_arr) of the Duffing model
                  trajectory — plotted in green for qualitative comparison

    Returns
    -------
    matplotlib.figure.Figure
    """
    x, y = _prepare_xy(data, remove_mean)
    z    = np.asarray(z_array, dtype=np.float64)
    N    = len(x)

    fig = plt.figure(figsize=(10, 7))
    ax  = fig.add_subplot(111, projection="3d")
    ax.set_title(title, fontsize=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("dT/dt")
    ax.set_zlabel(zlabel)

    cmap = LinearSegmentedColormap.from_list("blue_red", ["blue", "red"])
    norm = Normalize(0, N - 2)

    points   = np.column_stack([x, y, z]).reshape(-1, 1, 3)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = Line3DCollection(
        segments, cmap=cmap, norm=norm, linewidth=1.2, alpha=0.85
    )
    lc.set_array(np.arange(N - 1, dtype=float))
    ax.add_collection3d(lc)

    ax.set_xlim(float(x.min()), float(x.max()))
    ax.set_ylim(float(y.min()), float(y.max()))
    ax.set_zlim(float(z.min()), float(z.max()))

    fig.colorbar(lc, ax=ax, label="Time (earlier → later)", shrink=0.55, pad=0.1)

    if duffing_xyz is not None:
        xd, yd, zd = duffing_xyz
        ax.plot(
            np.asarray(xd), np.asarray(yd), np.asarray(zd),
            color="limegreen", linewidth=0.8, alpha=0.65,
            label="Duffing model",
        )
        ax.legend(loc="upper left", fontsize=9)

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def animate_phase_diagram_3d(
    data: dict,
    title: str,
    xlabel: str,
    z_array: np.ndarray,
    zlabel: str,
    tail_months: int = 12,
    save_path: str | None = None,
    fps: int = 15,
    dpi: int = 150,
    remove_mean: bool = False,
) -> animation.FuncAnimation:
    """
    Animated 3D phase diagram.

    Three layers update each frame:
    - Gray line  : full trajectory from frame 0 to current
    - Red line   : tail of the last tail_months × NDOTS frames
    - Blue dot   : current position in phase space

    Note: blit=False is required because matplotlib's 3D axes do not
    support blitting (all artists share the same renderer layer).

    Parameters
    ----------
    data        : dict from pipeline.load_output()
    title       : figure title
    xlabel      : x-axis label
    z_array     : pre-computed z values of shape (NTD,)
    zlabel      : z-axis label
    tail_months : months of history shown in the red tail (default 12)
    save_path   : if given, save as .mp4 via ffmpeg
    fps         : frames per second (default 15)
    dpi         : resolution (default 150)
    remove_mean : if True, subtract mean(T) before plotting

    Returns
    -------
    matplotlib.animation.FuncAnimation
    """
    x, y  = _prepare_xy(data, remove_mean)
    z     = np.asarray(z_array, dtype=np.float64)
    year  = data["year"]
    month = data["month"]
    irest = data["irest"]

    NDOTS       = int(irest.max()) + 1
    tail_frames = tail_months * NDOTS
    N           = len(x)

    fig = plt.figure(figsize=(10, 7))
    ax  = fig.add_subplot(111, projection="3d")
    ax.set_title(title, fontsize=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("dT/dt")
    ax.set_zlabel(zlabel)
    ax.set_xlim(float(x.min()), float(x.max()))
    ax.set_ylim(float(y.min()), float(y.max()))
    ax.set_zlim(float(z.min()), float(z.max()))

    line_full, = ax.plot([], [], [], color="gray", linewidth=1.0, alpha=0.7)
    line_tail, = ax.plot([], [], [], "r-", linewidth=1.6)
    dot_curr,  = ax.plot([], [], [], "bo", markersize=5)
    time_text  = ax.text2D(
        0.02, 0.95, "", transform=ax.transAxes, fontsize=11, va="top"
    )

    def _init():
        line_full.set_data_3d([], [], [])
        line_tail.set_data_3d([], [], [])
        dot_curr.set_data_3d([], [], [])
        time_text.set_text("")
        return line_full, line_tail, dot_curr, time_text

    def _update(num: int):
        start = max(num - tail_frames, 0)
        line_full.set_data_3d(x[: num + 1], y[: num + 1], z[: num + 1])
        line_tail.set_data_3d(
            x[start : num + 1], y[start : num + 1], z[start : num + 1]
        )
        dot_curr.set_data_3d([x[num]], [y[num]], [z[num]])
        time_text.set_text(f"{int(year[num]):04d} {int(month[num]):02d}")
        return line_full, line_tail, dot_curr, time_text

    ani = animation.FuncAnimation(
        fig,
        _update,
        frames=N,
        init_func=_init,
        interval=int(1000 / fps),
        blit=False,
        repeat=False,
    )

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        ani.save(save_path, writer="ffmpeg", fps=fps, dpi=dpi)

    return ani


# ---------------------------------------------------------------------------
# Self-test (no network, no file I/O, no display)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    7 tests covering compute_z, plot_phase_diagram_3d, and
    animate_phase_diagram_3d on synthetic data.

    Uses the Agg backend so the test passes in headless environments.
    """
    plt.switch_backend("Agg")
    print("Running self-test …")

    NT    = 120
    NDOTS = 5
    NTD   = (NT - 1) * NDOTS + 1

    t_monthly = np.arange(NT, dtype=float)
    T_monthly = (
        25.0
        + 2.0 * np.sin(2.0 * np.pi * t_monthly / 12.0)
        + 0.5 * np.sin(2.0 * np.pi * t_monthly / 36.0)
    )

    t_fine  = np.linspace(0, NT - 1, NTD)
    T_fine  = np.interp(t_fine, t_monthly, T_monthly)
    dT_fine = np.gradient(T_fine)

    irest_arr     = np.tile(np.arange(NDOTS), NT)[:NTD]
    year_monthly  = 1975 + t_monthly.astype(int) // 12
    month_monthly = (t_monthly.astype(int) % 12) + 1
    year_fine     = np.repeat(year_monthly,  NDOTS)[:NTD]
    month_fine    = np.repeat(month_monthly, NDOTS)[:NTD]

    data = {
        "T":     T_fine,
        "dT":    dT_fine,
        "year":  year_fine.astype(np.int32),
        "month": month_fine.astype(np.int32),
        "irest": irest_arr.astype(np.int32),
    }
    z_synth = np.gradient(dT_fine)

    # --- 1. compute_z mode="accel" with z_array: length and values correct ---
    z1 = compute_z(data, mode="accel", z_array=z_synth)
    assert len(z1) == NTD, f"FAIL 1: length {len(z1)} != {NTD}"
    assert np.allclose(z1, z_synth), "FAIL 1: z1 does not match z_synth"
    print(f"  PASS 1: compute_z mode='accel' with z_array → length {NTD}, values match")

    # --- 2. compute_z mode="accel" fallback (no z_array): finite values ---
    z2 = compute_z(data, mode="accel")
    assert len(z2) == NTD, f"FAIL 2: length {len(z2)} != {NTD}"
    assert np.all(np.isfinite(z2)), "FAIL 2: fallback accel contains non-finite values"
    print(f"  PASS 2: compute_z mode='accel' fallback → {NTD} finite values")

    # --- 3. compute_z mode="phase": values in [0, 2π) ---
    z3 = compute_z(data, mode="phase")
    assert len(z3) == NTD, f"FAIL 3: length {len(z3)} != {NTD}"
    assert float(z3.min()) >= 0.0, f"FAIL 3: min phase {z3.min():.6f} < 0"
    assert float(z3.max()) < 2.0 * np.pi + 1e-9, (
        f"FAIL 3: max phase {z3.max():.6f} >= 2π"
    )
    print(
        f"  PASS 3: compute_z mode='phase' → [{z3.min():.4f}, {z3.max():.4f}] ⊂ [0, 2π)"
    )

    # --- 4. compute_z mode="phase" at month 1, irest=0 → phase ≈ 0 ---
    # The first element corresponds to month=1, irest=0 → θ = 2π*(0/12) = 0.
    first_phase = float(z3[0])
    assert first_phase < 1e-9, (
        f"FAIL 4: phase at month 1, irest=0 = {first_phase:.2e}, expected 0"
    )
    print(f"  PASS 4: compute_z mode='phase' at month 1, irest=0 ≈ 0  ({first_phase:.2e})")

    # --- 5. compute_z invalid mode raises ValueError ---
    raised = False
    try:
        compute_z(data, mode="invalid_mode")
    except ValueError:
        raised = True
    assert raised, "FAIL 5: expected ValueError for unknown mode"
    print("  PASS 5: compute_z invalid mode raises ValueError")

    # --- 6. plot_phase_diagram_3d returns a Figure ---
    fig = plot_phase_diagram_3d(
        data=data,
        title="Self-test 3D (accel)",
        xlabel="Temperature (°C)",
        z_array=z_synth,
        zlabel="d²T/dt²",
    )
    assert isinstance(fig, matplotlib.figure.Figure), (
        f"FAIL 6: plot_phase_diagram_3d returned {type(fig)}"
    )
    plt.close(fig)
    print("  PASS 6: plot_phase_diagram_3d returns a Figure")

    # --- 7. animate_phase_diagram_3d returns a FuncAnimation ---
    ani = animate_phase_diagram_3d(
        data=data,
        title="Self-test 3D animation",
        xlabel="Temperature (°C)",
        z_array=z_synth,
        zlabel="d²T/dt²",
        save_path=None,
    )
    assert isinstance(ani, animation.FuncAnimation), (
        f"FAIL 7: animate_phase_diagram_3d returned {type(ani)}"
    )
    plt.close("all")
    print("  PASS 7: animate_phase_diagram_3d returns a FuncAnimation")

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
