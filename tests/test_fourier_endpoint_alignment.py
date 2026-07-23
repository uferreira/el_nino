"""Regression tests for calendar-aligned Fourier endpoints."""

import numpy as np

from el_nino import pipeline


def test_sst_index_fourier_window_starts_in_terminal_month(monkeypatch, tmp_path):
    """A January-to-July record must be filtered as July-to-July."""
    months = np.array(list(range(1, 13)) + list(range(1, 8)), dtype=np.int32)
    years = np.array([2000] * 12 + [2001] * 7, dtype=np.int32)
    values = np.arange(len(months), dtype=np.float64)

    monkeypatch.setattr(
        pipeline.download,
        "load_sst",
        lambda **_kwargs: {
            "IYR": years,
            "MES": months,
            "ANOM12": values,
        },
    )
    monkeypatch.setattr(pipeline, "passa_baixa", lambda _h1, _h2, data: data.copy())
    monkeypatch.setattr(
        pipeline,
        "deri_fourier",
        lambda _ndots, data: (data.copy(), np.zeros_like(data), np.zeros_like(data)),
    )
    monkeypatch.setattr(pipeline, "compute_sigma", lambda *_args: (0.0, 0.0))

    result = pipeline.run_sst_index(
        index_key="nino12",
        local_file="unused.txt",
        ano_inicio=2000,
        HN1=10.0,
        HN2=9.0,
        NDOTS=1,
        output_file=str(tmp_path / "aligned.dat"),
    )

    assert result["MES"][0] == result["MES"][-1] == 7
    assert result["IYR"][0] == 2000
    assert result["ANOM"][0] == values[6]


def _identity_pipeline(raw, _months, _h1, _h2, ndots):
    assert ndots == 1
    zeros = np.zeros_like(raw)
    return raw.copy(), raw.copy(), zeros, zeros, 0.0, 0.0


def test_absolute_sst_fourier_window_starts_in_terminal_month(monkeypatch, tmp_path):
    months = np.array(list(range(1, 13)) + list(range(1, 8)), dtype=np.int32)
    years = np.array([2000] * 12 + [2001] * 7, dtype=np.int32)
    values = np.arange(len(months), dtype=np.float64)
    monkeypatch.setattr(
        pipeline.download,
        "load_sst",
        lambda **_kwargs: {"IYR": years, "MES": months, "SST0": values},
    )
    monkeypatch.setattr(pipeline, "_run_pipeline_steps", _identity_pipeline)

    result = pipeline.run_sst(
        local_file="unused.txt",
        ano_inicio=2000,
        HN1=10.0,
        HN2=9.0,
        NDOTS=1,
        output_file=str(tmp_path / "sst.dat"),
    )

    assert result["MES"][0] == result["MES"][-1] == 7
    assert result["SST0"][0] == values[6]


def test_sea_level_fourier_window_starts_in_terminal_month(monkeypatch, tmp_path):
    months = np.array(list(range(1, 13)) + list(range(1, 8)), dtype=np.int32)
    years = np.array([2000] * 12 + [2001] * 7, dtype=np.int32)
    values = np.arange(len(months), dtype=np.float64)
    monkeypatch.setattr(
        pipeline.download,
        "load_sea_level",
        lambda **_kwargs: {"IYR": years, "MES": months, "SL0": values},
    )
    monkeypatch.setattr(pipeline, "_run_pipeline_steps", _identity_pipeline)

    result = pipeline.run_sea_level(
        station_id="007",
        station_name="Palau",
        start_date="2000-01-01",
        HN1=10.0,
        HN2=9.0,
        NDOTS=1,
        output_file=str(tmp_path / "sea-level.dat"),
    )

    assert result["MES"][0] == result["MES"][-1] == 7
    assert result["SL0"][0] == values[6]
