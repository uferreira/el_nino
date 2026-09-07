"""Regression tests for the Fourier analysis window's calendar endpoints.

The window used to be derived by a heuristic that forced the start into the
same calendar month as the end (``_align_fourier_window``).  It is now an
explicit parameter — ``config.yaml`` ``filter.window`` for the pipeline, the
date selector for the website — and the default start is the month *after*
the end month, so the record spans a whole number of 12-month seasonal
cycles.  That is the stronger property: it keeps the endpoints of the sine
expansion in the same phase of the annual cycle *and* gives the monthly
climatology an equal number of samples for every calendar month.

The same rules run in the browser; ``test_fourier_window_parity.py`` checks
the two implementations against each other.
"""

import numpy as np
import pytest

from el_nino import pipeline


def _calendar(year0: int, month0: int, n: int):
    years, months = [], []
    y, m = year0, month0
    for _ in range(n):
        years.append(y)
        months.append(m)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return (np.array(years, dtype=np.int32),
            np.array(months, dtype=np.int32),
            np.arange(n, dtype=np.float64))


def _identity_pipeline(raw, _months, _h1, _h2, ndots):
    assert ndots == 1
    zeros = np.zeros_like(raw)
    return raw.copy(), raw.copy(), zeros, zeros, 0.0, 0.0


def _assert_whole_cycles(result):
    """Start month must be end month + 1, and the count a multiple of 12."""
    mes = result["MES"]
    assert int(mes[0]) == int(mes[-1]) % 12 + 1
    assert len(mes) % 12 == 0
    assert result["window"]["whole_cycles"] is True
    counts = np.bincount(mes, minlength=13)[1:]
    assert len(set(counts[counts > 0])) == 1, "calendar months unevenly sampled"


# ---------------------------------------------------------------------------
# Default window
# ---------------------------------------------------------------------------

def test_sst_index_default_window_spans_whole_cycles(monkeypatch, tmp_path):
    """A January-2000-to-July-2001 record is filtered as August 2000 to July 2001."""
    years, months, values = _calendar(2000, 1, 19)

    monkeypatch.setattr(
        pipeline.download, "load_sst",
        lambda **_kwargs: {"IYR": years, "MES": months, "ANOM12": values},
    )
    monkeypatch.setattr(pipeline, "passa_baixa", lambda _h1, _h2, data: data.copy())
    monkeypatch.setattr(
        pipeline, "deri_fourier",
        lambda _ndots, data: (data.copy(), np.zeros_like(data), np.zeros_like(data)),
    )
    monkeypatch.setattr(pipeline, "compute_sigma", lambda *_args: (0.0, 0.0))

    result = pipeline.run_sst_index(
        index_key="nino12", local_file="unused.txt", ano_inicio=2000,
        HN1=10.0, HN2=9.0, NDOTS=1,
        output_file=str(tmp_path / "aligned.dat"),
    )

    _assert_whole_cycles(result)
    assert int(result["MES"][0]) == 8 and int(result["IYR"][0]) == 2000
    assert int(result["MES"][-1]) == 7 and int(result["IYR"][-1]) == 2001
    assert result["ANOM"][0] == values[7]


def test_absolute_sst_default_window_spans_whole_cycles(monkeypatch, tmp_path):
    years, months, values = _calendar(2000, 1, 19)
    monkeypatch.setattr(
        pipeline.download, "load_sst",
        lambda **_kwargs: {"IYR": years, "MES": months, "SST0": values},
    )
    monkeypatch.setattr(pipeline, "_run_pipeline_steps", _identity_pipeline)

    result = pipeline.run_sst(
        local_file="unused.txt", ano_inicio=2000,
        HN1=10.0, HN2=9.0, NDOTS=1, output_file=str(tmp_path / "sst.dat"),
    )

    _assert_whole_cycles(result)
    assert result["SST0"][0] == values[7]


def test_sea_level_default_window_spans_whole_cycles(monkeypatch, tmp_path):
    years, months, values = _calendar(2000, 1, 19)
    monkeypatch.setattr(
        pipeline.download, "load_sea_level",
        lambda **_kwargs: {"IYR": years, "MES": months, "SL0": values},
    )
    monkeypatch.setattr(pipeline, "_run_pipeline_steps", _identity_pipeline)

    result = pipeline.run_sea_level(
        station_id="007", station_name="Palau", start_date="2000-01-01",
        HN1=10.0, HN2=9.0, NDOTS=1, output_file=str(tmp_path / "sea-level.dat"),
    )

    _assert_whole_cycles(result)
    assert result["SL0"][0] == values[7]


# ---------------------------------------------------------------------------
# Explicit windows
# ---------------------------------------------------------------------------

def test_explicit_window_is_honoured_exactly(monkeypatch, tmp_path):
    """A requested window is used as given, not snapped to a nicer month."""
    years, months, values = _calendar(2000, 1, 60)
    monkeypatch.setattr(
        pipeline.download, "load_sea_level",
        lambda **_kwargs: {"IYR": years, "MES": months, "SL0": values},
    )
    monkeypatch.setattr(pipeline, "_run_pipeline_steps", _identity_pipeline)

    result = pipeline.run_sea_level(
        station_id="007", station_name="Palau", start_date="2000-01-01",
        HN1=10.0, HN2=9.0, NDOTS=1, output_file=str(tmp_path / "sl.dat"),
        window_start="2001-03", window_end="2003-09",
    )

    win = result["window"]
    assert (win["start"], win["end"]) == ("2001-03", "2003-09")
    assert int(result["MES"][0]) == 3 and int(result["IYR"][0]) == 2001
    assert int(result["MES"][-1]) == 9 and int(result["IYR"][-1]) == 2003
    # Not a whole number of cycles — reported, never silently corrected.
    assert win["whole_cycles"] is False
    assert any("whole 12-month cycles" in note for note in win["notes"])


def test_window_reaching_before_the_record_uses_its_first_whole_cycle():
    """Asking for more history than a record holds must not break the cycles.

    This is what happens on the website when the visitor widens the window to
    take in the long tide-gauge records: each series falls back to the first
    month of its own record that still starts a whole 12-month cycle.
    """
    years, months, values = _calendar(1970, 4, 400)
    win = pipeline.resolve_fourier_window(years, months, "1905-01", "2001-07")
    assert win["start"] == "1970-08"      # first August at or after Apr 1970
    assert win["end"] == "2001-07"
    assert win["whole_cycles"] is True
    assert any("first whole-cycle start" in note for note in win["notes"])


def test_window_shorter_than_a_season_is_rejected():
    years, months, values = _calendar(2000, 1, 60)
    with pytest.raises(ValueError, match="at least 12 months"):
        pipeline.resolve_fourier_window(years, months, "2001-01", "2001-06")


def test_align_fourier_window_still_documents_the_old_rule():
    """The superseded helper is kept, and still does what it always did."""
    years, months, values = _calendar(2000, 1, 19)
    y, m, v = pipeline._align_fourier_window(years, months, values)
    assert int(m[0]) == int(m[-1]) == 7
    assert v[0] == values[6]
