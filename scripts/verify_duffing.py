"""
verify_duffing.py
=================
Task 1E: Numerical identity test — compare duffing.solve_duffing() (scipy RK45)
against a pure Python RK4 that exactly replicates the JavaScript rk4Step()
function (which is labeled "exact translation of NL3System.java / DoubleWell.java").

Outputs:
  data/output/duffing_java_vs_python.png
  (report data printed to stdout and returned as a dict)
"""

from __future__ import annotations

import math
import sys
import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------------------------
# Allow running from the repo root
# ------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from el_nino.duffing import default_params, solve_duffing


# ------------------------------------------------------------------
# Pure-Python RK4 replicating the JavaScript rk4Step() exactly
# (also labeled "exact translation of NL3System.java / DoubleWell.java")
# ------------------------------------------------------------------
W_ANN = 2.0 * math.pi / 12.0   # same as JS: const W_ANN = 2 * Math.PI / 12;

def rhs_java(t, X, Y, p):
    """
    The g(x,y,z,t) RHS from NL3System.java / DoubleWell.java as translated
    to JavaScript in animations.html (rk4Step / rhs inner function).

    dY/dt = K0 + K1·X + K2·X² + K3·X³ + K4·X⁴ + K5·X⁵
            + FA·cos(FF_rad)·cos(W·t) + FA·sin(FF_rad)·sin(W·t)
            + FA2·cos(FF2_rad)·cos(2W·t) + FA2·sin(FF2_rad)·sin(2W·t)
            + B·Y
    """
    FFr  = p["FF"]  * math.pi / 180.0
    FF2r = p["FF2"] * math.pi / 180.0
    return (
        p["K0"]
        + p["K1"] * X
        + p["K2"] * X * X
        + p["K3"] * X * X * X
        + p["K4"] * X * X * X * X
        + p["K5"] * X * X * X * X * X
        + p["FA"]  * math.cos(FFr)  * math.cos(W_ANN * t)
        + p["FA"]  * math.sin(FFr)  * math.sin(W_ANN * t)
        + p["FA2"] * math.cos(FF2r) * math.cos(2.0 * W_ANN * t)
        + p["FA2"] * math.sin(FF2r) * math.sin(2.0 * W_ANN * t)
        + p["B"] * Y
    )


def rk4_step(t, X, Y, p, h):
    """
    Fixed-step RK4, exactly matching the JavaScript rk4Step() function.

    k1x = h*Y
    k1y = h*rhs(t, X, Y)
    k2x = h*(Y + k1y/2)
    k2y = h*rhs(t+h/2, X+k1x/2, Y+k1y/2)
    k3x = h*(Y + k2y/2)
    k3y = h*rhs(t+h/2, X+k2x/2, Y+k2y/2)
    k4x = h*(Y + k3y)
    k4y = h*rhs(t+h,   X+k3x,   Y+k3y)
    X_new = X + (k1x + 2*k2x + 2*k3x + k4x)/6
    Y_new = Y + (k1y + 2*k2y + 2*k3y + k4y)/6
    """
    def rhs(tt, xx, yy):
        return rhs_java(tt, xx, yy, p)

    k1x = h * Y
    k1y = h * rhs(t, X, Y)

    k2x = h * (Y + k1y / 2.0)
    k2y = h * rhs(t + h / 2.0, X + k1x / 2.0, Y + k1y / 2.0)

    k3x = h * (Y + k2y / 2.0)
    k3y = h * rhs(t + h / 2.0, X + k2x / 2.0, Y + k2y / 2.0)

    k4x = h * (Y + k3y)
    k4y = h * rhs(t + h, X + k3x, Y + k3y)

    X_new = X + (k1x + 2.0 * k2x + 2.0 * k3x + k4x) / 6.0
    Y_new = Y + (k1y + 2.0 * k2y + 2.0 * k3y + k4y) / 6.0
    return X_new, Y_new


def run_rk4(params, x0, y0, t_start, t_end, dt):
    """Run the pure-Python RK4 and return t, X, Y arrays at every dt step."""
    n_steps = int(round((t_end - t_start) / dt))
    t_arr = np.empty(n_steps + 1)
    x_arr = np.empty(n_steps + 1)
    y_arr = np.empty(n_steps + 1)

    t, X, Y = t_start, x0, y0
    t_arr[0] = t; x_arr[0] = X; y_arr[0] = Y

    for i in range(n_steps):
        X, Y = rk4_step(t, X, Y, params, dt)
        t += dt
        t_arr[i + 1] = t
        x_arr[i + 1] = X
        y_arr[i + 1] = Y

    return t_arr, x_arr, y_arr


# ------------------------------------------------------------------
# Main comparison
# ------------------------------------------------------------------
def run_comparison(t_end=120.0, dt=0.1, x0=0.0, y0=0.0):
    params = default_params()

    # 1. scipy RK45 (Python translation, adaptive)
    sol = solve_duffing(params, x0=x0, y0=y0, t_start=0.0, t_end=t_end, dt=dt)
    t_rk45  = sol["t"]
    x_rk45  = sol["x"]
    y_rk45  = sol["y"]

    # 2. Pure-Python RK4 (JS/Java translation, fixed step = dt)
    t_rk4, x_rk4, y_rk4 = run_rk4(params, x0, y0, 0.0, t_end, dt)

    # Align arrays (both should have same length but guard for float edge)
    n = min(len(t_rk45), len(t_rk4))
    t_rk45 = t_rk45[:n]; x_rk45 = x_rk45[:n]; y_rk45 = y_rk45[:n]
    t_rk4  = t_rk4[:n];  x_rk4  = x_rk4[:n];  y_rk4  = y_rk4[:n]

    dx = np.abs(x_rk45 - x_rk4)
    dy = np.abs(y_rk45 - y_rk4)

    max_dx = float(np.max(dx))
    max_dy = float(np.max(dy))
    worst_t_x = float(t_rk4[np.argmax(dx)])
    worst_t_y = float(t_rk4[np.argmax(dy)])

    # PASS / FAIL
    THRESHOLD = 0.01
    passed = max_dx <= THRESHOLD and max_dy <= THRESHOLD
    result = "PASS" if passed else "FAIL"

    print(f"\n{'='*60}")
    print(f"Duffing Java->Python numerical identity test")
    print(f"  Integration:  0 – {t_end:.0f} months, dt = {dt}")
    print(f"  scipy RK45:   rtol=1e-6, atol=1e-8 (adaptive)")
    print(f"  Python RK4:   fixed step = {dt} (JS/Java translation)")
    print(f"  max |dX| = {max_dx:.6e}  @ t = {worst_t_x:.1f} months")
    print(f"  max |dY| = {max_dy:.6e}  @ t = {worst_t_y:.1f} months")
    print(f"  Threshold:    {THRESHOLD}")
    print(f"  Result: {result}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    axes[0].plot(t_rk45, x_rk45, "b-", lw=1.2, alpha=0.8, label="scipy RK45 (Python)")
    axes[0].plot(t_rk4,  x_rk4,  "r--", lw=0.9, alpha=0.7, label="RK4 fixed-step (JS/Java)")
    axes[0].set_ylabel("X (model units)")
    axes[0].set_title(f"Duffing Equation: scipy RK45 vs RK4 fixed-step   —   {result}  "
                       f"(max|dX|={max_dx:.2e}, max|dY|={max_dy:.2e})")
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t_rk45, y_rk45, "b-", lw=1.2, alpha=0.8)
    axes[1].plot(t_rk4,  y_rk4,  "r--", lw=0.9, alpha=0.7)
    axes[1].set_ylabel("Y = dX/dt")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(t_rk4, dx, "m-",  lw=1.0, alpha=0.9, label="|dX|")
    axes[2].plot(t_rk4, dy, "c--", lw=1.0, alpha=0.9, label="|dY|")
    axes[2].axhline(THRESHOLD, color="r", ls=":", lw=1.2, label=f"threshold={THRESHOLD}")
    axes[2].set_ylabel("|d|")
    axes[2].set_xlabel("t (months)")
    axes[2].legend(fontsize=9)
    axes[2].grid(True, alpha=0.3)
    axes[2].set_yscale("log")

    plt.tight_layout()
    out_path = Path(__file__).parent.parent / "data" / "output" / "duffing_java_vs_python.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Plot saved -> {out_path}")

    return {
        "max_dx": max_dx, "max_dy": max_dy,
        "worst_t_x": worst_t_x, "worst_t_y": worst_t_y,
        "passed": passed, "result": result,
        "t": t_rk4, "x_rk45": x_rk45, "x_rk4": x_rk4,
        "y_rk45": y_rk45, "y_rk4": y_rk4,
    }


if __name__ == "__main__":
    run_comparison()
