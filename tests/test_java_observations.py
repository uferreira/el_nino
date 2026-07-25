"""Integrity checks for the observational legacy Java simulation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = (
    ROOT
    / "legacy-java"
    / "observations-2013"
    / "sva.2_filter_10_9_1950.1_2013.01.dat"
)
CURRENT = (
    ROOT
    / "docs"
    / "java"
    / "observations-2013"
    / "sva.2_filter_10_9_1950.1_2026.06.dat"
)
JAVA_PAGE = ROOT / "docs" / "java" / "observations-2013" / "index.html"
WRAPPER_PAGE = ROOT / "docs" / "java-simulation.html"


def _fields(line: bytes) -> tuple[float, float, int, int, int]:
    values = [value.strip() for value in line.decode("ascii").split(";")]
    return float(values[0]), float(values[1]), *(int(value) for value in values[2:])


def test_current_java_data_preserves_the_complete_2013_file_byte_for_byte():
    """Updating the end date must never revise the historical Java input."""
    baseline = BASELINE.read_bytes()
    current = CURRENT.read_bytes()

    assert current.startswith(baseline)
    assert current[len(baseline) :].startswith(b"   24.28;   1.46; 2013;  1; 1\n")


def test_current_java_data_is_ordered_and_reaches_june_2026():
    rows = [_fields(line) for line in CURRENT.read_bytes().splitlines()]
    dates = [(year, month, point) for _, _, year, month, point in rows]

    assert len(dates) == len(set(dates))
    assert dates == sorted(dates)
    assert dates[-1] == (2026, 6, 0)
    assert rows[-1][:2] == (26.01, -0.45)


def test_java_pages_select_the_updated_data_and_offer_a_standalone_view():
    java_html = JAVA_PAGE.read_text(encoding="utf-8")
    wrapper_html = WRAPPER_PAGE.read_text(encoding="utf-8")

    assert '<param name="final_year" value="2026.0">' in java_html
    assert '<param name="Final_Month" value="6.0">' in java_html
    assert 'value="sva.2_filter_10_9_1950.1_2026.06.dat"' in java_html
    assert 'data-simulation="observations-2026"' in wrapper_html
    assert 'id="standalone-link"' in wrapper_html
