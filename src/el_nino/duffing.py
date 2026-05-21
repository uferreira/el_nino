"""
el_nino.duffing
===============
Generalised Duffing / double-well oscillator — Python translation of the
Java applet DoubleWell.java / NL3System.java (DoubleWell.21.5, Blair Fraser).

The model is a periodically forced, damped nonlinear oscillator whose
double-well potential produces the characteristic figure-eight attractor
that closely matches the observed ENSO phase diagram (T vs dT/dt).

Physical interpretation
-----------------------
X  = sea surface temperature (or sea level anomaly) at some proxy location.
Y  = dX/dt  — rate of change.
The system evolves in the (X, Y) phase plane; the trajectory is the
ENSO attractor.

Double-well potential V(X) = −K1 X²/2 − K3 X⁴/4
    With K1 > 0 and K3 < 0 the potential has two minima (warm El Niño
    and cool La Niña states) separated by an unstable fixed point at X=0.
    Periodic forcing (trade-wind annual cycle, FA) drives the trajectory
    to flip between the two wells.

This is the inverse problem: find the simplest nonlinear oscillator
whose attractor matches the observed ENSO phase diagram. The Duffing
oscillator is the simplest such system — it has the minimum number of
degrees of freedom and the minimum polynomial order needed to reproduce
the double-well topology of ENSO dynamics.

References
----------
Duffing, G. (1918). Erzwungene Schwingungen bei veränderlicher Eigenfrequenz.
Lorenz, E. N. (1963). Deterministic Nonperiodic Flow. JAS 20, 130–141.
Wyrtki, K. (1985). Water displacements in the Pacific and the genesis of
    El Niño cycles. J. Geophys. Res. 90, 7129–7132.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

from el_nino.pipeline import load_output


# ---------------------------------------------------------------------------
# Default parameters (from dwsimulate.html, the fitted Java applet values)
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "K0": 0.0,
    "K1": +0.121847,
    "K2": 0.0,
    "K3": -0.03046,
    "K4": 0.0,
    "K5": 0.0,
    "FA":  +0.4873,
    "FF":  -60.0,
    "FA2":  0.0,
    "FF2":  0.0,
    "B":  -0.35465,
    "W":   0.523599,   # 2π/12 rad/month — annual forcing frequency
}


def default_params() -> dict:
    """
    Return the fitted Duffing parameters from the original Java applet
    (dwsimulate.html, Blair Fraser / DoubleWell.21.5).

    These five non-zero parameters define a minimal double-well oscillator
    that reproduces the ENSO attractor topology:

        K1 = +0.121847   linear restoring (positive → double-well)
        K3 = −0.03046    cubic restoring  (negative → bounded)
        FA = +0.4873     annual forcing amplitude (trade-wind cycle)
        FF = −60°        annual forcing phase
        B  = −0.35465    damping coefficient (negative → dissipative)
        W  = 0.523599    angular frequency = 2π/12 rad/month

    All other polynomial coefficients (K0, K2, K4, K5, FA2, FF2) are zero.

    Returns
    -------
    dict
        Copy of the default parameter dictionary; safe to modify.
    """
    return dict(_DEFAULTS)


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------

def duffing_rhs(t: float, state: np.ndarray, params: dict) -> list[float]:
    """
    Right-hand side of the generalised Duffing / double-well ODE.

    The second-order equation X'' = f(X, X', t) is written as the
    first-order system:

        dX/dt = Y
        dY/dt = K0 + K1·X + K2·X² + K3·X³ + K4·X⁴ + K5·X⁵
                + FA·cos(FF·π/180)·cos(W·t)
                + FA·sin(FF·π/180)·sin(W·t)
                + FA2·cos(FF2·π/180)·cos(2W·t)
                + FA2·sin(FF2·π/180)·sin(2W·t)
                + B·Y

    The forcing term FA·[cos(FF)·cos(Wt) + sin(FF)·sin(Wt)]
    = FA·cos(W·t − FF) is the annual trade-wind cycle.
    FF is the phase of annual forcing in degrees (FF < 0 means the
    forcing lags the calendar year by |FF|/360 × 12 months).

    Parameters
    ----------
    t : float
        Current time in months.
    state : array-like of shape (2,)
        [X, Y] — current position and velocity.
    params : dict
        Keys: K0, K1, K2, K3, K4, K5, FA, FF, FA2, FF2, B, W.
        Missing keys default to zero except W (defaults to 2π/12).

    Returns
    -------
    [dX/dt, dY/dt] : list of float
    """
    X, Y = state[0], state[1]

    K0  = params.get("K0",  0.0)
    K1  = params.get("K1",  0.0)
    K2  = params.get("K2",  0.0)
    K3  = params.get("K3",  0.0)
    K4  = params.get("K4",  0.0)
    K5  = params.get("K5",  0.0)
    FA  = params.get("FA",  0.0)
    FF  = params.get("FF",  0.0)
    FA2 = params.get("FA2", 0.0)
    FF2 = params.get("FF2", 0.0)
    B   = params.get("B",   0.0)
    W   = params.get("W",   2.0 * math.pi / 12.0)

    FF_rad  = FF  * math.pi / 180.0
    FF2_rad = FF2 * math.pi / 180.0

    dXdt = Y
    dYdt = (
        K0
        + K1 * X
        + K2 * X * X
        + K3 * X * X * X
        + K4 * X * X * X * X
        + K5 * X * X * X * X * X
        + FA  * math.cos(FF_rad)  * math.cos(W * t)
        + FA  * math.sin(FF_rad)  * math.sin(W * t)
        + FA2 * math.cos(FF2_rad) * math.cos(2.0 * W * t)
        + FA2 * math.sin(FF2_rad) * math.sin(2.0 * W * t)
        + B * Y
    )

    return [dXdt, dYdt]


# ---------------------------------------------------------------------------
# ODE solver
# ---------------------------------------------------------------------------

def solve_duffing(
    params: dict,
    x0: float,
    y0: float,
    t_start: float = 0.0,
    t_end: float = 600.0,
    dt: float = 0.1,
) -> dict:
    """
    Integrate the Duffing equation using scipy RK45.

    Equivalent to the RKF45 (Runge-Kutta-Fehlberg) integrator in
    NL3System.java, but uses scipy's adaptive step-size control for
    accuracy and efficiency.

    The default time span (600 months = 50 years) is long enough for the
    transient initial conditions to decay and the trajectory to settle
    onto the strange attractor.  For visual comparisons with NOAA data
    (1975–present, ~600 months), set t_end to match the data length.

    Parameters
    ----------
    params : dict
        Duffing parameters — see duffing_rhs for keys.  Use
        default_params() as a starting point.
    x0 : float
        Initial condition for X (temperature or sea level at t_start).
    y0 : float
        Initial condition for Y = dX/dt.
    t_start : float
        Start time in months (default 0.0 = January 1975 if you align
        with the SST data).
    t_end : float
        End time in months (default 600.0 = 50 years).
    dt : float
        Requested output time step in months (default 0.1).
        The solver uses smaller internal steps automatically.

    Returns
    -------
    dict with keys:
        t : ndarray — time points (months)
        x : ndarray — X trajectory
        y : ndarray — Y = dX/dt trajectory
    """
    t_eval = np.arange(t_start, t_end + dt * 0.5, dt)

    sol = solve_ivp(
        fun=duffing_rhs,
        t_span=(t_start, t_end),
        y0=[x0, y0],
        method="RK45",
        t_eval=t_eval,
        args=(params,),
        rtol=1e-6,
        atol=1e-8,
        dense_output=False,
    )

    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    return {
        "t": sol.t,
        "x": sol.y[0],
        "y": sol.y[1],
    }


# ---------------------------------------------------------------------------
# Parameter fitting
# ---------------------------------------------------------------------------

def fit_duffing_to_data(
    data_file: str,
    method: str = "least_squares",
) -> dict:
    """
    Fit Duffing model coefficients to the observed ENSO phase diagram.

    This is the inverse problem: find the simplest nonlinear oscillator
    (minimal polynomial degree, minimal number of parameters) whose
    attractor in (X, dX/dt) phase space matches the filtered ENSO
    trajectory from the pipeline output file.

    The Duffing oscillator is the canonical choice because:
    * K1 > 0, K3 < 0 gives a double-well potential, reproducing the
      two preferred states (El Niño / La Niña) of ENSO.
    * Annual forcing (FA, FF) captures the dominant seasonal modulation
      of ENSO variability.
    * A single damping coefficient B (negative) represents all
      dissipative processes in the ocean–atmosphere system.

    The residual is minimised using scipy.optimize.minimize (Nelder-Mead),
    with the five non-zero parameters from dwsimulate.html as starting
    point.  The cost function is the mean squared "equation error":
    at each observed (T, dT/dt, t) data point, the model predicts
    d²T/dt² = f(T, dT/dt, t); the observed d²T/dt² is estimated by
    numerical differentiation of the dT/dt column.  This avoids
    solving the ODE at each iteration.

    Parameters
    ----------
    data_file : str
        Path to a .dat file produced by pipeline.run_sst or
        pipeline.run_sea_level.  Expected columns: T; dT/dt; year; month; irest.
    method : str
        Optimisation method label (currently only 'least_squares' is
        implemented; the label is kept for future extension).

    Returns
    -------
    dict with keys:
        params     : dict — fitted Duffing parameters
        residual   : float — RMS equation error (same units as d²T/dt²)
        t          : ndarray — model time (months from start)
        x_model    : ndarray — model X trajectory (from solve_duffing)
        x_observed : ndarray — observed X (all data points)
    """
    # ── Load data ───────────────────────────────────────────────────────
    data = load_output(data_file)
    T_obs  = data["T"]
    dT_obs = data["dT"]
    N      = len(T_obs)

    # Infer NDOTS: irest cycles 0..NDOTS-1, so NDOTS = max(irest)+1.
    NDOTS = int(data["irest"].max()) + 1
    dt    = 1.0 / NDOTS                  # months per step (e.g. 0.2 for NDOTS=5)

    # Time array: t=0 at the first data point.
    t_arr = np.arange(N, dtype=np.float64) * dt

    # Numerical second derivative d²T/dt² from the dT/dt column.
    # numpy.gradient uses second-order central differences at interior points.
    d2T_obs = np.gradient(dT_obs, dt)

    # ── Equation-error cost function ────────────────────────────────────
    W = 2.0 * np.pi / 12.0

    def _model_acc(params_vec: np.ndarray) -> np.ndarray:
        """Evaluate the model RHS (= d²T/dt²) at all observed points."""
        K0, K1, K2, K3, K4, K5, FA, FF_deg, FA2, FF2_deg, B = params_vec
        FF_r  = FF_deg  * np.pi / 180.0
        FF2_r = FF2_deg * np.pi / 180.0
        return (
            K0
            + K1 * T_obs
            + K2 * T_obs ** 2
            + K3 * T_obs ** 3
            + K4 * T_obs ** 4
            + K5 * T_obs ** 5
            + FA  * np.cos(FF_r)  * np.cos(W * t_arr)
            + FA  * np.sin(FF_r)  * np.sin(W * t_arr)
            + FA2 * np.cos(FF2_r) * np.cos(2.0 * W * t_arr)
            + FA2 * np.sin(FF2_r) * np.sin(2.0 * W * t_arr)
            + B * dT_obs
        )

    def _cost(params_vec: np.ndarray) -> float:
        residuals = _model_acc(params_vec) - d2T_obs
        return float(np.mean(residuals ** 2))

    # Starting point: the fitted values from dwsimulate.html
    p0 = np.array([
        0.0,       # K0
        0.121847,  # K1
        0.0,       # K2
       -0.03046,   # K3
        0.0,       # K4
        0.0,       # K5
        0.4873,    # FA
       -60.0,      # FF  (degrees)
        0.0,       # FA2
        0.0,       # FF2 (degrees)
       -0.35465,   # B
    ])

    opt = minimize(
        _cost,
        p0,
        method="Nelder-Mead",
        options={"maxiter": 20_000, "xatol": 1e-7, "fatol": 1e-10, "adaptive": True},
    )

    # ── Unpack fitted parameters ─────────────────────────────────────────
    K0, K1, K2, K3, K4, K5, FA, FF_deg, FA2, FF2_deg, B = opt.x
    fitted = {
        "K0": float(K0),  "K1": float(K1),  "K2": float(K2),
        "K3": float(K3),  "K4": float(K4),  "K5": float(K5),
        "FA": float(FA),  "FF": float(FF_deg),
        "FA2": float(FA2), "FF2": float(FF2_deg),
        "B": float(B),
        "W": W,
    }

    residual = float(np.sqrt(opt.fun))

    # ── Solve ODE once with fitted params for trajectory comparison ──────
    t_end = float(t_arr[-1])
    sol = solve_duffing(
        fitted,
        x0=float(T_obs[0]),
        y0=float(dT_obs[0]),
        t_start=0.0,
        t_end=t_end,
        dt=dt,
    )

    return {
        "params":     fitted,
        "residual":   residual,
        "t":          sol["t"],
        "x_model":    sol["x"],
        "x_observed": T_obs,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Verify solve_duffing with the default parameters from dwsimulate.html.

    Checks:
    1. Output arrays have the expected length.
    2. X stays bounded (no divergence — the cubic term K3 < 0 ensures this).
    3. Y changes sign (the trajectory oscillates; a constant Y means the
       solver stopped or the attractor collapsed to a fixed point).
    4. The trajectory settles into a bounded attractor after a transient
       (max|X| in the second half is similar to max|X| in the first half).
    """
    print("Running duffing self-test …")

    params = default_params()
    T_MONTHS = 120      # 10 years
    DT       = 0.1      # months per output step

    sol = solve_duffing(params, x0=0.0, y0=0.0,
                        t_start=0.0, t_end=T_MONTHS, dt=DT)

    expected_n = int(round(T_MONTHS / DT)) + 1
    actual_n   = len(sol["t"])

    # 1. Length (±1 for floating-point edge at t_end)
    assert abs(actual_n - expected_n) <= 1, (
        f"FAIL 1: expected ~{expected_n} points, got {actual_n}"
    )
    print(f"  PASS 1: output length = {actual_n}  (expected ~{expected_n})")

    # 2. Bounded X
    max_abs_x = float(np.max(np.abs(sol["x"])))
    assert max_abs_x < 100.0, f"FAIL 2: |X| = {max_abs_x:.2f} — trajectory diverged"
    print(f"  PASS 2: |X| bounded  (max|X| = {max_abs_x:.4f})")

    # 3. Y changes sign (oscillating)
    assert np.any(sol["y"] > 0) and np.any(sol["y"] < 0), (
        "FAIL 3: Y does not change sign — trajectory not oscillating"
    )
    print(f"  PASS 3: Y oscillates  (min = {sol['y'].min():.4f}, max = {sol['y'].max():.4f})")

    # 4. Bounded attractor — second half amplitude ≈ first half
    mid  = len(sol["x"]) // 2
    amp1 = float(np.max(np.abs(sol["x"][:mid])))
    amp2 = float(np.max(np.abs(sol["x"][mid:])))
    ratio = amp2 / amp1 if amp1 > 0 else float("inf")
    assert 0.5 < ratio < 2.0, (
        f"FAIL 4: attractor not stable — amplitude ratio = {ratio:.3f}"
    )
    print(f"  PASS 4: attractor stable  (amp ratio second/first half = {ratio:.3f})")

    print("\nAll tests passed.")


if __name__ == "__main__":
    _self_test()
