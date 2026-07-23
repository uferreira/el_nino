"""Regression checks for the generated website and its update automation."""

from __future__ import annotations

import colorsys
import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_PAGE = ROOT / "docs" / "phase_diagrams.html"
COMPARE_PAGE = ROOT / "docs" / "compare.html"
DUFFING_PAGE = ROOT / "docs" / "duffing_simulation.html"
UPDATE_SCRIPT = ROOT / "scripts" / "update_website.py"
UPDATE_WORKFLOW = ROOT / ".github" / "workflows" / "update_data.yml"


def _load_update_website():
    spec = importlib.util.spec_from_file_location("update_website", UPDATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_phase_diagram_extra_stations_follow_calendar_time():
    """Palau must not stop at Oct 2020 while the master clock reaches 2026."""
    html = PHASE_PAGE.read_text(encoding="utf-8")

    assert "function obs1AdvanceExtrasToDate(" in html
    assert "function clsAdvanceExtrasToDate(" in html
    assert re.search(
        r"obs1AdvanceExtrasToDate\([^;]*callaoData\.year\[OBS1\.calIdx\]",
        html,
    )
    assert re.search(
        r"clsAdvanceExtrasToDate\([^;]*callaoData\.year\[CLS\.calIdx\]",
        html,
    )


def test_compare_history_has_readable_contrast():
    """Past trajectories need enough opacity and width to remain visible."""
    html = COMPARE_PAGE.read_text(encoding="utf-8")
    history = re.search(
        r"cmpOffCtx\.globalAlpha\s*=\s*([0-9.]+);\s*"
        r"cmpOffCtx\.strokeStyle\s*=\s*color;\s*"
        r"cmpOffCtx\.lineWidth\s*=\s*([0-9.]+);",
        html,
    )
    assert history is not None
    assert float(history.group(1)) >= 0.55
    assert float(history.group(2)) >= 2.0


def test_historical_palettes_reserve_red_for_the_recent_year():
    """History must stay distinct from red and readable on each background."""
    compare_html = COMPARE_PAGE.read_text(encoding="utf-8")
    phase_html = PHASE_PAGE.read_text(encoding="utf-8")
    duffing_html = DUFFING_PAGE.read_text(encoding="utf-8")

    def palette(html: str, name: str) -> list[str]:
        match = re.search(rf"const {name}\s*=\s*\[(.*?)\];", html, re.S)
        assert match
        return re.findall(r"#[0-9a-fA-F]{6}", match.group(1))

    def hue_and_white_contrast(value: str) -> tuple[float, float]:
        rgb = tuple(int(value[offset : offset + 2], 16) / 255 for offset in (1, 3, 5))
        hue = colorsys.rgb_to_hsv(*rgb)[0] * 360
        linear = tuple(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in rgb
        )
        luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
        return hue, 1.05 / (luminance + 0.05)

    compare_colors = palette(compare_html, "CMP_PALETTE")
    seasonal_colors = palette(phase_html, "Q_COLORS") + palette(
        duffing_html, "Q_COLORS"
    )
    for color in compare_colors + seasonal_colors:
        hue, _ = hue_and_white_contrast(color)
        assert 30 < hue < 330, f"historical red-like color: {color}"
    for color in compare_colors:
        _, contrast = hue_and_white_contrast(color)
        assert contrast >= 3.0, f"history is too pale on white: {color}"

    assert "const CMP_RECENT_COLOR = '#dc2626';" in compare_html


def test_phase_diagrams_use_a_fixed_twelve_month_recent_window():
    """Every observed phase diagram must distinguish the rolling last year."""
    phase_html = PHASE_PAGE.read_text(encoding="utf-8")
    compare_html = COMPARE_PAGE.read_text(encoding="utf-8")

    assert "const RECENT_WINDOW_MONTHS=12;" in phase_html
    assert "function recentWindowStartYM(currentYM)" in phase_html
    assert "tail[0].ym < firstRecentYM" in phase_html
    assert "point.irest === 0" in phase_html
    assert "CURRENT_POINT_RADIUS" in phase_html
    assert "const CMP_RECENT_WINDOW_MONTHS = 12;" in compare_html
    assert "function cmpRecentWindowStartYM(currentYM)" in compare_html
    assert "tail[0].ym < firstRecentYM" in compare_html
    assert "point.irest === 0" in compare_html
    assert "CMP_CURRENT_POINT_RADIUS" in compare_html
    assert 'id="cmp-sl-tail"' not in compare_html


def test_duffing_attractor_has_synchronized_side_panels():
    """The attractor must retain the three diagnostic views requested by users."""
    html = DUFFING_PAGE.read_text(encoding="utf-8")

    for canvas_id in ("att-pot-canvas", "att-time-canvas", "att-phase-canvas"):
        assert f'id="{canvas_id}"' in html
    assert "const ATT_SIDE_TRAIL_CYCLES=3;" in html
    assert "function attPotential(" in html
    assert "function attDrawPotential(" in html
    assert "function attDrawTimeHistory(" in html
    assert "function attDrawPhaseTrail(" in html
    assert "function attDrawSidePanels(" in html
    assert "ATT.frames[k].push({x:X, y:Y, year:yearIdx, t:t});" in html
    assert "attDrawSidePanels();" in html
    assert "K5*x**6/6" in html
    assert "File%3ADuffing_oscillator.webm" in html


def test_phase_plot_axes_are_derived_from_every_embedded_series():
    """Updated observations must never outgrow hard-coded phase-plot axes."""
    phase_html = PHASE_PAGE.read_text(encoding="utf-8")
    duffing_html = DUFFING_PAGE.read_text(encoding="utf-8")
    compare_html = COMPARE_PAGE.read_text(encoding="utf-8")
    talara_match = re.search(
        r"const talaraData = \{\s*x:\s*\[([^\]]+)\],\s*y:\s*\[([^\]]+)\],",
        phase_html,
    )
    assert talara_match
    talara_x = [float(value) for value in talara_match.group(1).split(",")]
    talara_y = [float(value) for value in talara_match.group(2).split(",")]
    talara_mean = sum(talara_x) / len(talara_x)
    assert max(value - talara_mean for value in talara_x) > 300
    assert min(talara_y) < -60
    for html in (phase_html, duffing_html):
        assert "function phaseAutoDomain(" in html
        assert "function phaseAutoConfig(" in html
        for data_name in (
            "nino3Data",
            "nino34Data",
            "nino4Data",
            "talaraData",
            "laLibData",
            "honoluluData",
            "palauData",
        ):
            assert re.search(
                rf"phaseAutoConfig\([^)]*\b{data_name}\b",
                html,
            )

    assert "const OBS1_DOM_CAL=phaseAutoDomain(callaoData" in phase_html
    assert "const CLS_DOM_CAL=phaseAutoDomain(callaoData" in phase_html
    assert "const CMP_DOM_CAL=phaseAutoDomain(callaoData" in duffing_html
    assert "function cmpFitDomain(" in compare_html
    assert "cmpComputeDomains(params.norm, preps)" in compare_html



def test_update_script_covers_current_data_pages():
    uw = _load_update_website()
    names = {path.name for path in uw.HTML_FILES}

    assert "phase_diagrams.html" in names
    assert "duffing_simulation.html" in names
    assert "animations.html" not in names


def test_successful_but_old_station_data_is_reported():
    uw = _load_update_website()
    state = {
        "stations": {
            "talara": {
                "name": "Talara",
                "as_of": "2025-08",
                "ok": True,
                "stale": True,
            }
        }
    }

    notes = uw._stale_notes(state)

    assert notes == [
        "Talara sea level data as of August 2025 "
        "(no later month passes coverage checks)"
    ]


def test_workflow_stages_every_generated_document():
    workflow = UPDATE_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r"git add\s+docs(?:/|\s)", workflow)


def test_long_reconstructed_station_gap_is_reported():
    uw = _load_update_website()
    state = {
        "stations": {
            "talara": {
                "name": "Talara",
                "as_of": "2025-08",
                "ok": True,
                "stale": True,
                "interpolated_months": 68,
                "longest_gap_months": 26,
            }
        }
    }

    notes = uw._stale_notes(state)

    assert any(
        "68 reconstructed missing months" in note
        and "longest gap: 26 months" in note
        for note in notes
    )
