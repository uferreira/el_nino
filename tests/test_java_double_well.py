"""Layout checks for the legacy double-well Java simulation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JAVA_PAGE = ROOT / "docs" / "java" / "double-well" / "index.html"
WRAPPER_PAGE = ROOT / "docs" / "java-simulation.html"


def test_double_well_preserves_the_complete_java_surface():
    """The text area below the phase portrait must not be clipped."""
    java_html = JAVA_PAGE.read_text(encoding="utf-8")

    assert 'width="600" height="950"' in java_html
    assert "const appletWidth=600;" in java_html
    assert "const appletHeight=950;" in java_html
    assert "appletStage.clientWidth/appletWidth" in java_html
    assert "appletWrap.style.transform=`scale(${scale})`" in java_html
    assert "appletHeight*scale" in java_html


def test_double_well_wrapper_uses_the_revised_page():
    wrapper_html = WRAPPER_PAGE.read_text(encoding="utf-8")

    assert "java/double-well/index.html?v=20260725b" in wrapper_html
