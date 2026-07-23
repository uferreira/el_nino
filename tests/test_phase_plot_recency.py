"""Regression tests for the rolling-year phase-diagram emphasis."""

from __future__ import annotations

import numpy as np

from el_nino.plots import _recent_window_start_index, plot_phase_diagram


def _sample_data() -> dict[str, np.ndarray]:
    months = np.arange(18)
    year = 2024 + (6 + months) // 12
    month = (6 + months) % 12 + 1
    return {
        "T": np.sin(months / 3),
        "dT": np.cos(months / 3),
        "year": year,
        "month": month,
        "irest": np.zeros(months.size, dtype=int),
    }


def test_recent_window_is_exactly_twelve_calendar_months():
    data = _sample_data()

    start = _recent_window_start_index(data["year"], data["month"], 12)

    assert len(data["year"]) - start == 12
    assert (int(data["year"][start]), int(data["month"][start])) == (2025, 1)


def test_static_phase_diagram_distinguishes_history_recent_year_and_endpoint():
    fig = plot_phase_diagram(
        _sample_data(),
        title="test",
        xlabel="T",
        xlim=[-2, 2],
        ylim=[-2, 2],
    )
    ax = fig.axes[0]

    colors = [line.get_color() for line in ax.lines]
    assert "#777777" in colors
    assert "#dc2626" in colors
    assert "#ffbf00" in colors
    assert ax.collections  # monthly point markers
