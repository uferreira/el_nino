"""
tests/test_resilience.py
========================
Resilience against transient UHSLC network failures.

Two behaviours are covered:

test_fetch_*
    ``download._fetch`` retries transient timeouts / dropped connections with
    exponential backoff, but never retries an HTTP error (e.g. 404) and gives
    up with a RuntimeError once the backoff schedule is exhausted.

test_one_station_fails_others_patched
    ``update_website.main`` must not let a single flaky sea level station
    (e.g. Callao when UHSLC times out) abort the whole update. The page's
    generated region is rebuilt as a whole, so the failing station has to keep
    the raw series already published there while every other dataset is
    refreshed, and the script must not exit non-zero.

Run with:
    pytest tests/test_resilience.py -v
"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from el_nino import download


# ---------------------------------------------------------------------------
# _fetch retry behaviour
# ---------------------------------------------------------------------------

def test_fetch_retries_transient_then_succeeds(monkeypatch):
    """Two transient failures, then success: _fetch should return the good response."""
    good = MagicMock()
    good.raise_for_status = MagicMock()  # no error
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("dropped")
        return good

    sleeps: list = []
    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download.time, "sleep", lambda s: sleeps.append(s))

    resp = download._fetch("http://example/x", "test station")

    assert resp is good
    assert calls["n"] == 3
    # Slept before attempts 2 and 3 using the first two configured backoffs.
    assert sleeps == list(download.RETRY_BACKOFFS[:2])


def test_fetch_gives_up_after_retries(monkeypatch):
    """Persistent timeouts exhaust the backoff schedule and raise RuntimeError."""
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        raise requests.exceptions.Timeout("slow")

    sleeps: list = []
    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(RuntimeError, match="after"):
        download._fetch("http://example/x", "test station")

    # Initial attempt + one per backoff.
    assert calls["n"] == len(download.RETRY_BACKOFFS) + 1
    assert sleeps == list(download.RETRY_BACKOFFS)


def test_fetch_http_error_not_retried(monkeypatch):
    """A 404 must fail immediately without any retry/backoff."""
    err = requests.exceptions.HTTPError()
    err.response = MagicMock(status_code=404)

    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=err)
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        return resp

    sleeps: list = []
    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(RuntimeError, match="HTTP 404"):
        download._fetch("http://example/x", "test station")

    assert calls["n"] == 1
    assert sleeps == []


# ---------------------------------------------------------------------------
# update_website.main: one station fails, others still patched
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_website.py"


def _load_update_website():
    spec = importlib.util.spec_from_file_location("update_website", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MIN_CONFIG = """\
filter:
  HN1: 10.0
  HN2: 9.0
  NDOTS: 5
  window:
    start: null
    end: null
    base_year: 1975
sst:
  local_file: "{local_file}"
  ano_inicio: 1975
sst_indices:
  - {{key: "nino3",  label: "NINO3"}}
  - {{key: "nino4",  label: "NINO4"}}
  - {{key: "nino34", label: "NINO3.4"}}
stations:
  callao:   {{id: "093", name: "Callao",   start_date: "1905-01-01"}}
  honolulu: {{id: "057", name: "Honolulu", start_date: "1905-01-01"}}
"""


_FRESHNESS_MARKER = (
    '<p class="data-freshness"><!--DATA_FRESHNESS-->old<!--/DATA_FRESHNESS--></p>'
)

# Marker values that make "was this dataset rewritten?" readable in an assert.
_OLD_VALUE = 9.99
_NEW_VALUE = 1.11


_YEARS = [2000] * 12 + [2001] * 12
_MONTHS = list(range(1, 13)) * 2


def _raw_full(value: float, drop_last: int = 0) -> dict:
    """Pipeline-shaped raw record (what run_* returns), 24 months.

    ``drop_last`` shortens the record from the end, which is how a run that
    fell back to a stale source looks: same series, fewer recent months.
    """
    end = len(_YEARS) - drop_last
    return {"values": [value] * end,
            "IYR": _YEARS[:end], "MES": _MONTHS[:end]}


def _raw_published(value: float) -> dict:
    """JS-shaped raw record (what the page carries), 24 months."""
    return {"values": [value] * 24, "year": _YEARS, "month": _MONTHS}


def _published_values(html: str, var_name: str) -> list[float]:
    """Read one dataset's values back out of the page's RAW_SERIES block."""
    import re
    m = re.search(
        rf"{var_name}:\s*\{{[^{{}}]*?values:\[([^\]]*)\]", html, re.DOTALL
    )
    assert m, f"{var_name} missing from the generated region"
    return [float(v) for v in m.group(1).split(",") if v.strip()]


def _setup(uw, tmp_path, monkeypatch, *, callao_fails, argv_extra=None,
           prior_freshness=None, drop_last=0):
    """
    Wire update_website's I/O to temp locations and stub the pipeline runners.

    Returns (index_path, freshness_path). Callao raises RuntimeError when
    ``callao_fails`` is True; every other station succeeds.
    """
    dummy_new = {"x": [0.0, 1.0], "y": [1.0, 2.0],
                 "year": [2000, 2000], "month": [1, 2], "irest": [0, 0]}
    monkeypatch.setattr(uw, "_load_dat", lambda p: dict(dummy_new))
    monkeypatch.setattr(uw, "_count_monthly", lambda p: 2)

    def _result():
        return {"IYR": [2000, 2001], "MES": [1, 12],
                "raw_full": _raw_full(_NEW_VALUE, drop_last)}

    monkeypatch.setattr(uw, "_run_sst_nino12",
                        lambda *a, **k: (Path("x.dat"), _result()))
    monkeypatch.setattr(uw, "_run_sst_index",
                        lambda *a, **k: (Path("x.dat"), _result()))

    def fake_run_sl(st, *a, **k):
        if callao_fails and st["name"] == "Callao":
            raise RuntimeError("UHSLC timeout on ERDDAP and RQD")
        return Path("x.dat"), _result()

    monkeypatch.setattr(uw, "_run_sl", fake_run_sl)

    # index.html: an already-published region carrying every dataset, plus the
    # freshness marker, so a rebuild has something to preserve.
    from collections import OrderedDict
    published = OrderedDict(
        (var, _raw_published(_OLD_VALUE)) for var in uw.DATASETS)
    idx = tmp_path / "index.html"
    idx.write_text(
        "<html>\n<script>\n"
        + uw._build_data_region(published, 10.0, 9.0, 5, 1975)
        + "\n</script>\n" + _FRESHNESS_MARKER + "\n</html>\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(uw, "HTML_FILES", [idx])
    monkeypatch.setattr(uw, "OUT_DIR", tmp_path / "out")
    fresh = tmp_path / "freshness.json"
    monkeypatch.setattr(uw, "FRESHNESS_FILE", fresh)
    if prior_freshness is not None:
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_text(json.dumps(prior_freshness), encoding="utf-8")

    local_file = tmp_path / "sst_hist.txt"
    local_file.write_text("header\n", encoding="utf-8")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        _MIN_CONFIG.format(local_file=local_file.as_posix()), encoding="utf-8"
    )

    argv = ["update_website.py", "--no-push", "--config", str(cfg_path)]
    argv += argv_extra or []
    monkeypatch.setattr(uw.sys, "argv", argv)
    return idx, fresh


def test_one_station_fails_others_patched(tmp_path, monkeypatch, capsys):
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=True)

    # Should complete without SystemExit despite Callao failing.
    uw.main()

    final = idx.read_text(encoding="utf-8")
    # Callao failed → the region keeps the values already published.
    assert _published_values(final, "callaoData")[0] == _OLD_VALUE
    # A healthy station and the SST block carry the fresh values.
    assert _published_values(final, "honoluluData")[0] == _NEW_VALUE
    assert _published_values(final, "observedData")[0] == _NEW_VALUE
    # The region is still well formed and still drives the browser filter.
    assert uw.DATA_BEGIN in final and uw.DATA_END in final
    assert "EnsoFourier.runAll(RAW_SERIES" in final

    err = capsys.readouterr().err
    assert "Callao" in err


def test_failed_station_marked_stale_in_freshness(tmp_path, monkeypatch):
    uw = _load_update_website()
    prior = {
        "last_refreshed": "2026-06-05",
        "stations": {
            "callao": {"name": "Callao", "last_success": "2026-06-05",
                       "as_of": "2026-05", "ok": True},
        },
    }
    idx, fresh = _setup(uw, tmp_path, monkeypatch,
                        callao_fails=True, prior_freshness=prior)

    uw.main()

    state = json.loads(fresh.read_text(encoding="utf-8"))
    # Callao is now stale but keeps its last-known-good month.
    assert state["stations"]["callao"]["ok"] is False
    assert state["stations"]["callao"]["as_of"] == "2026-05"
    # A healthy station recorded a fresh success.
    assert state["stations"]["honolulu"]["ok"] is True
    assert state["last_refreshed"] is not None

    # The index.html footnote surfaces the stale station subtly.
    final = idx.read_text(encoding="utf-8")
    assert "Data last refreshed:" in final
    assert "Callao sea level data as of May 2026 (fetch pending)" in final


def test_sl_only_leaves_sst_series_untouched(tmp_path, monkeypatch):
    uw = _load_update_website()

    # --sl-only must not even call the SST runners.
    def _boom(*a, **k):
        raise AssertionError("SST pipeline ran under --sl-only")

    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False,
                    argv_extra=["--sl-only"])
    monkeypatch.setattr(uw, "_run_sst_nino12", _boom)
    monkeypatch.setattr(uw, "_run_sst_index", _boom)

    uw.main()

    final = idx.read_text(encoding="utf-8")
    # SST/NINO series keep the published values …
    assert _published_values(final, "observedData")[0] == _OLD_VALUE
    assert _published_values(final, "nino3Data")[0] == _OLD_VALUE
    # … while sea level stations were refreshed.
    assert _published_values(final, "callaoData")[0] == _NEW_VALUE
    assert _published_values(final, "honoluluData")[0] == _NEW_VALUE


def test_sst_only_and_sl_only_mutually_exclusive(tmp_path, monkeypatch):
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False,
                    argv_extra=["--sst-only", "--sl-only"])
    with pytest.raises(SystemExit) as exc:
        uw.main()
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Regression guard: published data must only ever move forwards
# ---------------------------------------------------------------------------

def test_older_data_is_refused(tmp_path, monkeypatch, capsys):
    """A run whose data ends earlier than the page must abort before writing.

    This is the failure mode of an unreachable source or a stale local cache:
    the pipeline succeeds, produces a shorter record, and would quietly
    un-publish real observations.
    """
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False, drop_last=3)
    before = idx.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        uw.main()
    assert exc.value.code == 1

    # Nothing was written: the page still carries the newer published data.
    assert idx.read_text(encoding="utf-8") == before
    assert _published_values(before, "observedData")[0] == _OLD_VALUE

    err = capsys.readouterr().err
    assert "would move back from Dec 2001 to Sep 2001" in err
    assert "--allow-older" in err


def test_allow_older_overrides_the_guard(tmp_path, monkeypatch, capsys):
    """The escape hatch writes the older data, but says so on stderr."""
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False,
                    drop_last=3, argv_extra=["--allow-older"])

    uw.main()

    final = idx.read_text(encoding="utf-8")
    assert _published_values(final, "observedData")[0] == _NEW_VALUE
    err = capsys.readouterr().err
    assert "WARNING" in err and "would move back" in err


def test_equal_or_newer_data_passes_the_guard(tmp_path, monkeypatch):
    """The common case — same or later last month — is not obstructed."""
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False)

    uw.main()

    assert _published_values(idx.read_text(encoding="utf-8"),
                             "observedData")[0] == _NEW_VALUE


def test_guard_ignores_datasets_that_were_not_rerun(tmp_path, monkeypatch):
    """--sl-only must not trip the guard on the SST series it never touched."""
    uw = _load_update_website()
    idx, _ = _setup(uw, tmp_path, monkeypatch, callao_fails=False,
                    argv_extra=["--sl-only"])

    uw.main()   # must not raise

    final = idx.read_text(encoding="utf-8")
    assert _published_values(final, "observedData")[0] == _OLD_VALUE
    assert _published_values(final, "callaoData")[0] == _NEW_VALUE
