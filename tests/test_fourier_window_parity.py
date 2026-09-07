"""
Python <-> JavaScript parity for the Fourier window and the filter.

The website no longer ships pre-filtered arrays: it embeds the raw monthly
observations and re-runs the filter in the browser so the analysis window can
be changed interactively.  That makes ``docs/assets/js/fourier-filter.js`` a
second implementation of ``src/el_nino/filter.py`` and of the window logic in
``src/el_nino/pipeline.py``, and two implementations drift.

These tests run the real JavaScript under Node against the real Python on the
same inputs and require them to agree.  If Node is not installed the tests
skip rather than fail, so the suite still runs in a bare environment.

Where each side does the work
-----------------------------
    window selection : pipeline.resolve_fourier_window / select_fourier_window
                       EnsoFourier.resolveWindow / selectWindow
    low-pass filter  : filter.passa_baixa      / EnsoFourier.passaBaixa
    interp + deriv   : filter.deri_fourier     / EnsoFourier.deriFourier
    full dataset     : pipeline._run_pipeline_steps + _write_dat
                       EnsoFourier.runDataset
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import numpy as np
import pytest

from el_nino import pipeline
from el_nino.filter import deri_fourier, passa_baixa

REPO = Path(__file__).resolve().parents[1]
JS_FILTER = REPO / "docs" / "assets" / "js" / "fourier-filter.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not JS_FILTER.exists(),
    reason="Node.js or docs/assets/js/fourier-filter.js not available",
)

HN1, HN2, NDOTS, BASE_YEAR = 10.0, 9.0, 5, 1975


def _run_node(script: str, payload: dict) -> dict:
    """Execute a snippet with EnsoFourier loaded and INPUT bound to payload."""
    prelude = f"const F = require({str(JS_FILTER)!r});\n" \
              f"const INPUT = {json.dumps(payload)};\n"
    proc = subprocess.run(
        ["node", "-e", prelude + textwrap.dedent(script)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _monthly_calendar(year0: int, month0: int, n: int):
    years, months = [], []
    y, m = year0, month0
    for _ in range(n):
        years.append(y)
        months.append(m)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return np.array(years, dtype=np.int32), np.array(months, dtype=np.int32)


def _synthetic_series(n: int) -> np.ndarray:
    """Seasonal cycle + an ENSO-band oscillation + intra-seasonal noise.

    The high-frequency term is what the low-pass filter has to remove, so it
    makes any disagreement between the two sigmoid windows visible.
    """
    t = np.arange(n, dtype=float)
    return (
        25.0
        + 2.0 * np.sin(2 * np.pi * t / 12.0)
        + 0.8 * np.sin(2 * np.pi * t / 47.0 + 0.4)
        + 0.3 * np.cos(2 * np.pi * t / 5.0)
    )


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------

WINDOW_CASES = [
    (None, None),               # defaults: base year, whole 12-month cycles
    ("1990-01", "2020-12"),     # fully inside every record
    ("1905-01", None),          # earlier than the record -> whole-cycle start
    ("1975-09", "2026-08"),     # the site's headline window
    ("1980-03", "2020-07"),     # deliberately not a whole number of cycles
]


@pytest.mark.parametrize("start,end", WINDOW_CASES)
@pytest.mark.parametrize("year0,month0,n", [(1975, 1, 619), (1949, 9, 923)])
def test_window_resolution_matches(start, end, year0, month0, n):
    years, months = _monthly_calendar(year0, month0, n)
    py = pipeline.resolve_fourier_window(years, months, start, end, BASE_YEAR)

    js = _run_node(
        """
        const raw = {year: INPUT.year, month: INPUT.month,
                     values: INPUT.year.map(() => 0)};
        const w = F.resolveWindow(raw, {start: INPUT.start, end: INPUT.end},
                                  INPUT.baseYear);
        console.log(JSON.stringify({start: w.start, end: w.end,
                                    nMonths: w.nMonths,
                                    wholeCycles: w.wholeCycles,
                                    notes: w.notes.length}));
        """,
        {"year": years.tolist(), "month": months.tolist(),
         "start": start, "end": end, "baseYear": BASE_YEAR},
    )

    assert js["start"] == py["start"]
    assert js["end"] == py["end"]
    assert js["nMonths"] == py["n_months"]
    assert js["wholeCycles"] is py["whole_cycles"]
    assert js["notes"] == len(py["notes"])


def test_default_window_spans_whole_seasonal_cycles():
    """The default start must make every calendar month equally represented.

    This is the property the old endpoint-alignment heuristic only
    approximated, and the reason the site's default start is September when
    the record ends in August.
    """
    years, months = _monthly_calendar(1975, 1, 620)   # ends 2026-08
    win = pipeline.resolve_fourier_window(years, months, None, None, BASE_YEAR)
    assert win["start"] == "1975-09"
    assert win["end"] == "2026-08"
    assert win["n_months"] % 12 == 0
    assert win["whole_cycles"] is True
    assert win["notes"] == []


# ---------------------------------------------------------------------------
# The filter itself
# ---------------------------------------------------------------------------

def test_passa_baixa_matches():
    series = _synthetic_series(612)
    py = passa_baixa(HN1, HN2, series)
    js = _run_node(
        """
        console.log(JSON.stringify(Array.from(
          F.passaBaixa(INPUT.HN1, INPUT.HN2, INPUT.series))));
        """,
        {"series": series.tolist(), "HN1": HN1, "HN2": HN2},
    )
    assert np.allclose(js, py, rtol=0, atol=1e-9)


def test_deri_fourier_matches():
    filtered = passa_baixa(HN1, HN2, _synthetic_series(612))
    sst, vst, ast = deri_fourier(NDOTS, filtered)
    js = _run_node(
        """
        const d = F.deriFourier(INPUT.NDOTS, INPUT.series);
        console.log(JSON.stringify({SST: Array.from(d.SST),
                                    VST: Array.from(d.VST),
                                    AST: Array.from(d.AST)}));
        """,
        {"series": filtered.tolist(), "NDOTS": NDOTS},
    )
    assert np.allclose(js["SST"], sst, rtol=0, atol=1e-9)
    assert np.allclose(js["VST"], vst, rtol=0, atol=1e-9)
    assert np.allclose(js["AST"], ast, rtol=0, atol=1e-9)


# ---------------------------------------------------------------------------
# Whole dataset, the way each side actually runs it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("deseasonalize", [True, False])
@pytest.mark.parametrize("start,end", WINDOW_CASES[:4])
def test_full_dataset_matches(deseasonalize, start, end):
    """EnsoFourier.runDataset must reproduce the .dat columns exactly.

    Both sides round to two decimals, matching the F7.2 format the Fortran
    and the Python pipeline write, so the comparison is exact rather than
    approximate.
    """
    years, months = _monthly_calendar(1975, 1, 619)
    series = _synthetic_series(619)

    y_w, m_w, v_w, win = pipeline.select_fourier_window(
        years, months, series, start, end, BASE_YEAR
    )
    if deseasonalize:
        filtered, interp, vel, _, _, _ = pipeline._run_pipeline_steps(
            v_w, m_w, HN1, HN2, NDOTS
        )
    else:
        filtered = passa_baixa(HN1, HN2, v_w)
        interp, vel, _ = deri_fourier(NDOTS, filtered)

    js = _run_node(
        """
        const raw = {label: 'test', unit: 'x', group: 'sst',
                     deseasonalize: INPUT.deseasonalize,
                     values: INPUT.values, year: INPUT.year, month: INPUT.month};
        const r = F.runDataset(raw,
          {HN1: INPUT.HN1, HN2: INPUT.HN2, NDOTS: INPUT.NDOTS,
           baseYear: INPUT.baseYear},
          {start: INPUT.start, end: INPUT.end});
        console.log(JSON.stringify({x: r.x, y: r.y, year: r.year,
                                    month: r.month, irest: r.irest,
                                    start: r.window.start, end: r.window.end}));
        """,
        {"values": series.tolist(), "year": years.tolist(),
         "month": months.tolist(), "deseasonalize": deseasonalize,
         "HN1": HN1, "HN2": HN2, "NDOTS": NDOTS, "baseYear": BASE_YEAR,
         "start": start, "end": end},
    )

    assert js["start"] == win["start"] and js["end"] == win["end"]
    assert js["x"] == [round(float(v), 2) + 0.0 for v in np.round(interp, 2)]
    assert js["y"] == [round(float(v), 2) + 0.0 for v in np.round(vel, 2)]

    # Calendar columns follow _write_dat: IREST 0 marks an original month.
    n_months = len(v_w)
    assert len(js["x"]) == (n_months - 1) * NDOTS + 1
    assert js["irest"][:NDOTS + 1] == list(range(NDOTS)) + [0]
    assert js["year"][0] == int(y_w[0]) and js["month"][0] == int(m_w[0])
    assert js["year"][-1] == int(y_w[-1]) and js["month"][-1] == int(m_w[-1])
