"""Scientific invariants for the translated Fourier and SSH pipelines."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from el_nino import download
from el_nino.filter import deri_fourier, passa_baixa
from el_nino.pipeline import _align_fourier_window, _compute_climatology


def test_fourier_derivatives_use_the_true_monthly_time_scale():
    """Analytical derivatives must use NT-1 monthly intervals, not NT points."""
    nt = 120
    nm1 = nt - 1
    ndots = 5
    mode = 7
    amplitude = 2.0
    monthly_t = np.arange(nt, dtype=float)
    signal = amplitude * np.sin(mode * monthly_t * np.pi / nm1)

    _, velocity, acceleration = deri_fourier(ndots, signal)

    fine_t = np.arange(nm1 * ndots + 1, dtype=float) / ndots
    phase = mode * fine_t * np.pi / nm1
    expected_velocity = amplitude * (mode * np.pi / nm1) * np.cos(phase)
    expected_acceleration = -amplitude * (mode * np.pi / nm1) ** 2 * np.sin(phase)

    np.testing.assert_allclose(velocity, expected_velocity, rtol=1e-11, atol=1e-11)
    np.testing.assert_allclose(
        acceleration,
        expected_acceleration,
        rtol=1e-11,
        atol=1e-11,
    )


def _constant_month(start: str, value: float) -> list[str]:
    times = pd.date_range(start, periods=pd.Period(start, freq="M").days_in_month * 24,
                          freq="h", tz="UTC")
    return [f"{value},{timestamp.isoformat()}" for timestamp in times]


def test_erddap_monthly_means_preserve_calendar_and_reject_sparse_month(
    monkeypatch,
):
    """Missing/sparse SSH months must be reconstructed, not time-compressed."""
    rows = []
    rows.extend(_constant_month("2000-01-01", 100.0))
    # February is entirely absent.
    rows.extend(_constant_month("2000-03-01", 300.0))
    # One hour is not a representative April monthly mean.
    rows.append("1000.0,2000-04-01T00:00:00+00:00")
    rows.extend(_constant_month("2000-05-01", 500.0))
    response = SimpleNamespace(
        text="sea_level,time\nmm,UTC\n" + "\n".join(rows) + "\n"
    )

    monkeypatch.setattr(download, "_fetch", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(download, "_save_raw", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        download,
        "_load_rapid",
        lambda _station_id: pd.DataFrame(columns=["time_utc", "sl_mm"]),
    )

    result = download._load_sea_level_erddap("999", "Synthetic", "2000-01-01")

    assert result["IYR"].tolist() == [2000] * 5
    assert result["MES"].tolist() == [1, 2, 3, 4, 5]
    np.testing.assert_allclose(result["SL0"], [100, 200, 300, 400, 500])
    assert result["interpolated_months"] == 2
    assert result["low_coverage_months"] == 1

def test_filter_accepts_integer_input_without_changing_scientific_type():
    result = passa_baixa(10.0, 9.0, np.arange(24))

    assert result.dtype == np.float64
    assert np.isfinite(result).all()


@pytest.mark.parametrize(
    ("function", "args", "message"),
    [
        (passa_baixa, (10.0, 9.0, [1.0]), "at least"),
        (passa_baixa, (9.0, 10.0, [1.0, 2.0, 3.0]), "HN1"),
        (passa_baixa, (10.0, 10.0, [1.0, 2.0, 3.0]), "HN1"),
        (passa_baixa, (10.0, 9.0, [1.0, np.nan, 3.0]), "finite"),
        (deri_fourier, (0, [1.0, 2.0, 3.0]), "NDOTS"),
        (deri_fourier, (5, [[1.0, 2.0], [3.0, 4.0]]), "one-dimensional"),
    ],
)
def test_fourier_routines_reject_invalid_inputs(function, args, message):
    with pytest.raises(ValueError, match=message):
        function(*args)

def test_rapid_loader_selects_the_candidate_with_the_latest_observation(
    monkeypatch,
):
    def response(last_date: str, value: float) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=200,
            text=(
                "sea_level,time\n"
                "mm,UTC\n"
                f"{value},2026-01-01T00:00:00Z\n"
                f"{value},{last_date}T00:00:00Z\n"
            ),
        )

    responses = {
        "data/csv/fast": response("2026-01-31", 100.0),
        "stations/RAPID": response("2026-02-03", 200.0),
    }

    def fake_get(url, **_kwargs):
        return next(value for marker, value in responses.items() if marker in url)

    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download, "_save_raw", lambda *_args, **_kwargs: None)

    result = download._load_rapid("999")

    assert result["time_utc"].max() == pd.Timestamp("2026-02-03", tz="UTC")

def test_fourier_alignment_rejects_a_compressed_calendar_gap():
    with pytest.raises(ValueError, match="continuous monthly calendar"):
        _align_fourier_window(
            np.array([2000, 2000, 2000]),
            np.array([1, 2, 4]),
            np.array([1.0, 2.0, 4.0]),
        )


def test_climatology_rejects_missing_calendar_months():
    months = np.arange(1, 12)
    with pytest.raises(ValueError, match="all 12 calendar months"):
        _compute_climatology(months, months.astype(float))
