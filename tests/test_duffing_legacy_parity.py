"""Regression checks for parity with the legacy ALADO Java applet."""

from __future__ import annotations

import math
import re
from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "docs" / "duffing_simulation.html"
LEGACY = {
    "K1": 0.121847,
    "K3": -0.03046,
    "FA": 0.4873,
    "FF": -60.0,
    "B": -0.35465,
    "W": 0.523599,
}


def _control_value(name: str) -> float:
    html = PAGE.read_text(encoding="utf-8")
    match = re.search(rf'<input[^>]+id="nb-{name}"[^>]+value="([^"]+)"', html)
    assert match, f"missing numeric control nb-{name}"
    return float(match.group(1))


def _annual_strobe(parameters: dict[str, float]) -> list[tuple[float, float]]:
    """Integrate the displayed equation and sample the same month for 52 years."""
    x = y = t = 0.0
    dt = 0.1
    phase = math.radians(parameters["FF"])

    def acceleration(time: float, position: float, velocity: float) -> float:
        return (
            parameters["K1"] * position
            + parameters["K3"] * position**3
            + parameters["B"] * velocity
            + parameters["FA"] * math.cos(parameters["W"] * time - phase)
        )

    def step() -> None:
        nonlocal x, y, t
        k1x = y
        k1y = acceleration(t, x, y)
        k2x = y + dt * k1y / 2
        k2y = acceleration(t + dt / 2, x + dt * k1x / 2, y + dt * k1y / 2)
        k3x = y + dt * k2y / 2
        k3y = acceleration(t + dt / 2, x + dt * k2x / 2, y + dt * k2y / 2)
        k4x = y + dt * k3y
        k4y = acceleration(t + dt, x + dt * k3x, y + dt * k3y)
        x += dt * (k1x + 2 * k2x + 2 * k3x + k4x) / 6
        y += dt * (k1y + 2 * k2y + 2 * k3y + k4y) / 6
        t += dt

    for _ in range(10 * 12 * 10):
        step()

    points = []
    for _ in range(52):
        points.append((x, y))
        for _ in range(12 * 10):
            step()
    return points


def test_alado_defaults_match_the_java_legacy_coefficients_exactly():
    actual = {name: _control_value(name) for name in LEGACY}
    assert actual == LEGACY


def test_runtime_initialization_keeps_the_precise_number_input_values():
    html = PAGE.read_text(encoding="utf-8")
    function = re.search(
        r"function linkSlider\(slId, nbId, lblId, fmt\) \{(?P<body>.*?)\n\}",
        html,
        re.DOTALL,
    )
    assert function, "missing linkSlider initialization"
    assert "upd(nb.value);" in function.group("body")


def test_same_month_stays_on_the_java_legacy_narrow_strobe():
    parameters = {name: _control_value(name) for name in LEGACY}
    points = _annual_strobe(parameters)
    x_span = max(x for x, _ in points) - min(x for x, _ in points)
    y_span = max(y for _, y in points) - min(y for _, y in points)

    assert x_span > 1.5
    assert y_span < 0.35
    assert y_span / x_span < 0.2
