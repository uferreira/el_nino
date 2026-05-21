"""
tests/test_filter_vs_fortran.py
================================
Scientific validation: verify that the Python filter.py produces results
numerically identical to the reference Fortran program.

Three tests
-----------
test_python_matches_fortran
    End-to-end: compile the Fortran, run both programs on identical 5-year
    synthetic input, compare T and dT/dt column-by-column.  Skipped when
    gfortran is not installed.

test_filter_preserves_low_frequency
    Amplitude ratios in the passband and stopband: slow mode (≈17 months)
    must survive, fast mode (≈3 months) must be blocked.

test_deri_fourier_derivative_accuracy
    VST from deri_fourier must match the analytical derivative of an exact
    Fourier basis mode within 1 % at interior grid points.

Run with:
    pytest tests/test_filter_vs_fortran.py -v
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from el_nino.filter import deri_fourier, passa_baixa

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FORTRAN_SRC = Path(
    "/Users/uggopinho/Documents/estudos/ElNino/FORTRAN/"
    "filterfouriergr197501_202502.f"
)

# These filenames are hardcoded inside the Fortran source — do not change.
_FORT_INPUT  = "sst_combined_1975.2_2025.02_ENTRADA.dat"
_FORT_OUTPUT = "sva.2_filter_10_9_1975.2_2025.02_SAIDA.dat"


# ---------------------------------------------------------------------------
# Helper: synthetic data
# ---------------------------------------------------------------------------

def make_synthetic_input(
    n_years: int,
    start_year: int,
    start_month: int,
) -> tuple[Path, np.ndarray, np.ndarray, np.ndarray]:
    """
    Write a synthetic SST input file in the exact Fortran input format.

    Fortran FORMAT(I4,2X,I2,2X,F6.2) — right-justified columns separated
    by 2-space gaps.  Preceded by 20 blank header lines that the Fortran
    skips with DO 2383 I=1,20 / READ(1,2020).

    Signal: SST(t) = 25 + 2·sin(2π·t/12) + 0.5·sin(2π·t/36)

    Values are rounded to 2 decimal places because F6.2 stores exactly 2
    decimal digits.  The Python run must use these same rounded values so
    both programs operate on numerically identical input.

    Parameters
    ----------
    n_years     : total months = n_years * 12
    start_year  : first data year
    start_month : first data month (1..12)

    Returns
    -------
    tmp_path    : Path to the written temp file (caller should unlink)
    sst_rounded : float64 (n_months,) — values as written (F6.2 precision)
    years       : int32 (n_months,)
    months      : int32 (n_months,) with values in 1..12
    """
    n_months = n_years * 12
    t        = np.arange(n_months, dtype=float)
    sst_raw  = (
        25.0
        + 2.0 * np.sin(2.0 * np.pi * t / 12.0)
        + 0.5 * np.sin(2.0 * np.pi * t / 36.0)
    )
    sst_rounded = np.round(sst_raw, 2)

    years_list, months_list = [], []
    yr, mo = start_year, start_month
    for _ in range(n_months):
        years_list.append(yr)
        months_list.append(mo)
        mo += 1
        if mo > 12:
            mo, yr = 1, yr + 1

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".dat", delete=False, prefix="sst_synth_"
    )
    tmp_path = Path(tmp.name)

    for _ in range(20):
        tmp.write("\n")

    # FORMAT(I4,2X,I2,2X,F6.2)
    for yr_i, mo_i, sst_i in zip(years_list, months_list, sst_rounded):
        tmp.write(f"{yr_i:4d}  {mo_i:2d}  {sst_i:6.2f}\n")

    tmp.close()
    return (
        tmp_path,
        sst_rounded,
        np.array(years_list,  dtype=np.int32),
        np.array(months_list, dtype=np.int32),
    )


# ---------------------------------------------------------------------------
# Helper: Fortran compile + run
# ---------------------------------------------------------------------------

def compile_fortran(fortran_path: Path, exe_path: Path) -> bool:
    """
    Compile with gfortran -O2.  Returns False if gfortran is absent.
    """
    if shutil.which("gfortran") is None:
        return False
    result = subprocess.run(
        ["gfortran", "-O2", "-o", str(exe_path), str(fortran_path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def run_fortran(exe_path: Path, input_file: Path) -> list[str]:
    """
    Run the Fortran executable in an isolated temp directory.

    The program uses hardcoded input/output filenames, so we copy the
    synthetic input under the expected name and run from that directory.
    The output file is read inside the context manager before cleanup.

    Returns the lines of the Fortran output file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        shutil.copy(input_file, td / _FORT_INPUT)

        result = subprocess.run(
            [str(exe_path)],
            cwd=str(td),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Fortran executable failed (rc={result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

        out_path = td / _FORT_OUTPUT
        if not out_path.exists():
            raise RuntimeError(
                f"Fortran produced no output file '{_FORT_OUTPUT}'\n"
                f"stdout: {result.stdout}"
            )

        # Read inside the context so the file exists when we return.
        return out_path.read_text().splitlines()


# ---------------------------------------------------------------------------
# Helper: Python pipeline (mirrors Fortran main program exactly)
# ---------------------------------------------------------------------------

def run_python(
    sst: np.ndarray,
    months: np.ndarray,
    HN1: float = 10.0,
    HN2: float = 9.0,
    NDOTS: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Replicate the Fortran main program's pipeline in Python.

    Steps (identical order to Fortran):
    1. ANUAL[m] = mean(SST0 where MES==m) for m=1..12
    2. SST1 = SST0 - ANUAL[MES]          (remove annual cycle)
    3. passa_baixa(HN1, HN2, SST1) → SST2
    4. SST3 = SST2 + ANUAL[MES]          (re-add annual cycle)
    5. deri_fourier(NDOTS, SST3) → SST4, VST

    Returns SST4 and VST — the two numeric columns in the Fortran output file.
    """
    clim         = np.array([sst[months == m].mean() for m in range(1, 13)])
    clim_monthly = clim[months - 1]
    sst1         = sst - clim_monthly
    sst2         = passa_baixa(HN1, HN2, sst1)
    sst3         = sst2 + clim_monthly
    sst4, vst, _ = deri_fourier(NDOTS, sst3)
    return sst4, vst


# ---------------------------------------------------------------------------
# Helper: parse Fortran output
# ---------------------------------------------------------------------------

def parse_fortran_output(lines: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """
    Parse lines written by Fortran FORMAT 5766:
        ' F7.2;F7.2;I5;I3;I2'
    Returns (T_arr, dT_arr) as float64 arrays.
    """
    T_list, dT_list = [], []
    for line in lines:
        parts = line.strip().split(";")
        if len(parts) < 2:
            continue
        try:
            T_list.append(float(parts[0]))
            dT_list.append(float(parts[1]))
        except ValueError:
            continue
    return np.array(T_list, dtype=np.float64), np.array(dT_list, dtype=np.float64)


# ---------------------------------------------------------------------------
# Test 1 — End-to-end Fortran vs Python
# ---------------------------------------------------------------------------

def test_python_matches_fortran(tmp_path):
    """
    Run Fortran and Python on the same 5-year synthetic SST series and
    compare column by column.

    Both T and dT/dt must agree within 0.01, which equals the rounding
    precision of the Fortran F7.2 output format.  Any difference larger
    than this indicates a real algorithmic discrepancy, not just formatting.

    Skipped when gfortran is not installed or the Fortran source is absent.
    """
    if not FORTRAN_SRC.exists():
        pytest.skip(f"Fortran source not found: {FORTRAN_SRC}")

    exe = tmp_path / "fortran_filter"
    if not compile_fortran(FORTRAN_SRC, exe):
        pytest.skip(
            "gfortran not available or compilation failed — "
            "install gfortran to enable this test"
        )

    input_file, sst_rounded, _years, months = make_synthetic_input(
        n_years=5, start_year=1975, start_month=2
    )

    try:
        fort_lines = run_fortran(exe, input_file)
    finally:
        input_file.unlink(missing_ok=True)

    T_fort, dT_fort = parse_fortran_output(fort_lines)
    assert len(T_fort) > 0, "Fortran produced no parseable output"

    sst4_py, vst_py = run_python(sst_rounded, months)

    # Align lengths (should both equal NTD = (NT-1)*NDOTS+1 = 296 for 5 years).
    N       = min(len(T_fort), len(sst4_py))
    T_fort  = T_fort[:N];  dT_fort = dT_fort[:N]
    T_py    = sst4_py[:N]; dT_py   = vst_py[:N]

    err_T  = np.abs(T_fort - T_py)
    err_dT = np.abs(dT_fort - dT_py)

    # ── Comparison table (first 10 rows) ─────────────────────────────────
    print(
        f"\n{'Row':>4}  {'T_fort':>8}  {'T_py':>10}  {'|ΔT|':>10}  "
        f"{'dT_fort':>8}  {'dT_py':>10}  {'|ΔdT|':>10}"
    )
    print("-" * 74)
    for i in range(min(10, N)):
        print(
            f"{i + 1:4d}  {T_fort[i]:8.4f}  {T_py[i]:10.6f}  {err_T[i]:10.6f}  "
            f"{dT_fort[i]:8.4f}  {dT_py[i]:10.6f}  {err_dT[i]:10.6f}"
        )

    max_err_T  = float(err_T.max())
    max_err_dT = float(err_dT.max())
    print(f"\nMax |ΔT|  = {max_err_T:.6f}  (tolerance 0.01)")
    print(f"Max |ΔdT| = {max_err_dT:.6f}  (tolerance 0.01)")

    assert max_err_T  < 0.01, (
        f"T column mismatch: max |ΔT| = {max_err_T:.6f} ≥ 0.01"
    )
    assert max_err_dT < 0.01, (
        f"dT column mismatch: max |ΔdT| = {max_err_dT:.6f} ≥ 0.01"
    )


# ---------------------------------------------------------------------------
# Test 2 — Passband / stopband amplitude ratios
# ---------------------------------------------------------------------------

def test_filter_preserves_low_frequency():
    """
    Verify passa_baixa frequency response at the two spectral extremes.

    Strategy: use exact Fourier basis functions sin(IW·t·π/NM1).
    For integer IW the signal is zero at both endpoints t=0 and t=NM1,
    so passa_baixa's detrending step leaves it untouched — giving a clean
    single-mode input with no spectral leakage.

    Pass band: IW=7  → period = NM1/7 ≈ 17 months  → ratio must be > 0.9
    Stop band: IW=40 → period = NM1/40 ≈ 3 months   → ratio must be < 0.1
    """
    NT  = 120
    NM1 = NT - 1
    A   = 2.0
    t   = np.arange(NT, dtype=float)

    # ── Slow mode (passband) ─────────────────────────────────────────────
    IW_SLOW = 7                          # period ≈ 17 months
    y_slow  = A * np.sin(IW_SLOW * t * np.pi / NM1)
    stb     = passa_baixa(10.0, 9.0, y_slow)
    ratio   = np.sqrt(np.mean(stb ** 2)) / np.sqrt(np.mean(y_slow ** 2))
    print(f"\n  17-month amplitude ratio = {ratio:.6f}  (threshold > 0.90)")
    assert ratio > 0.9, (
        f"17-month mode suppressed (ratio={ratio:.4f}, expected > 0.9)"
    )

    # ── Fast mode (stopband) ─────────────────────────────────────────────
    IW_FAST = 40                         # period ≈ 3 months
    y_fast  = A * np.sin(IW_FAST * t * np.pi / NM1)
    stb     = passa_baixa(10.0, 9.0, y_fast)
    ratio   = np.sqrt(np.mean(stb ** 2)) / np.sqrt(np.mean(y_fast ** 2))
    print(f"  3-month  amplitude ratio = {ratio:.6f}  (threshold < 0.10)")
    assert ratio < 0.1, (
        f"3-month mode leaked (ratio={ratio:.6f}, expected < 0.1)"
    )


# ---------------------------------------------------------------------------
# Test 3 — Derivative accuracy
# ---------------------------------------------------------------------------

def test_deri_fourier_derivative_accuracy():
    """
    Verify that deri_fourier computes an accurate first derivative.

    Input: exact Fourier basis mode  y(t) = A·sin(IW₀·t·π/NM1)

    By the orthogonality of the sine basis on {1, …, NM1}, the Fourier
    coefficient for mode IW₀ equals A exactly:

        FOURIER[IW₀] = (2/NM1) Σ_{IT=1}^{NM1} A·sin²(IW₀·IT·π/NM1) = A

    so deri_fourier produces on the fine grid (s = 0..NTDM1):

        VST(s) = A · (IW₀·π/NT) · cos(IW₀·s·π/NTDM1)

    The analytical derivative of y w.r.t. the original monthly index t,
    evaluated at t = s·(NM1/NTDM1) = s/NDOTS (since NTDM1 = NM1·NDOTS):

        dT/dt(s) = A · (IW₀·π/NM1) · cos(IW₀·s·π/NTDM1)

    The ratio VST/dT/dt = NM1/NT = (NT−1)/NT ≈ 0.9917 for NT=120, giving
    a systematic discrepancy of 0.83 % — faithful to the Fortran (which
    also uses NT, not NM1, in the denominator).  The test checks that this
    residual stays below the 1 % threshold.

    For this exact mode, FIRST = STA[0] = 0 and HLAST = STA[NT−1] = 0
    (integer IW₀ → zero endpoints), so the trend-restoration term
    (HLAST−FIRST)/NM1 vanishes and does not affect the comparison.
    """
    NT    = 120
    NM1   = NT - 1
    NDOTS = 5
    NTD   = NM1 * NDOTS + 1   # 596
    NTDM1 = NTD - 1

    IW0 = 7
    A   = 2.0
    t   = np.arange(NT, dtype=float)
    y   = A * np.sin(IW0 * t * np.pi / NM1)

    _, vst, _ = deri_fourier(NDOTS, y)

    # Analytical derivative at fine-grid points.
    # Since NTDM1 = NM1·NDOTS, the argument IW₀·s·π/NTDM1 = IW₀·s·π/(NM1·NDOTS)
    # is identical to IW₀·(s/NDOTS)·π/NM1, confirming the fine-grid mapping.
    s          = np.arange(NTD, dtype=float)
    analytical = A * (IW0 * np.pi / NM1) * np.cos(IW0 * s * np.pi / NTDM1)

    # Skip the outermost 20 % of points at each end to avoid any endpoint
    # artefacts from the finite detrending step.
    interior = slice(NTD // 5, 4 * NTD // 5)
    err      = np.abs(vst[interior] - analytical[interior])
    amp      = float(np.abs(analytical[interior]).max())
    rel_err  = float(err.max()) / amp

    print(f"\n  Max relative derivative error = {rel_err:.4%}  (threshold 1.00%)")
    assert rel_err < 0.01, (
        f"Derivative error {rel_err:.4%} exceeds 1 % "
        f"(expected ≈ 0.83 % from the NT vs NM1 factor in the denominator)"
    )
