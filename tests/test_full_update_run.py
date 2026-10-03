"""
tests/test_full_update_run.py
=============================
A plain ``python scripts/update_website.py`` (no flags) must download and
process every SST index and every sea level station listed in config.yaml,
publish each one, and record each one in freshness.json.

Only the network is mocked (``download.requests.get``): the real download,
FD + RAPID merge, monthly aggregation, Fourier pipeline, page rebuild and
freshness bookkeeping all run. The synthetic sources are dated relative to
today, so the expected "last month" moves with the calendar:

    Fast Delivery (ERDDAP)  ends three months ago (FD normally lags)
    RAPID                   covers the two months after that, in full

so every station must end last month, which it can only do if the RAPID
months survive the merge and the coverage rules.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import numpy as np
import pandas as pd
import pytest
import yaml

from el_nino import download

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_website.py"
REAL_CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
WORKFLOW = ROOT / ".github" / "workflows" / "update_data.yml"

_NOW = pd.Timestamp(datetime.now(timezone.utc).strftime("%Y-%m-01"))
LAST_MONTH = _NOW - pd.DateOffset(months=1)      # expected end of SSH and SST
FD_END = _NOW - pd.DateOffset(months=2)          # first month FD no longer has


def _load_update_website():
    spec = importlib.util.spec_from_file_location("update_website", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Synthetic sources
# ---------------------------------------------------------------------------

def _noaa_text() -> str:
    """sstoi.indices from 1982-01 through last month."""
    lines = ["YR   MON  NINO1+2  ANOM   NINO3    ANOM   NINO4    ANOM NINO3.4    ANOM"]
    for ts in pd.date_range("1982-01-01", LAST_MONTH, freq="MS"):
        t = (ts.year - 1982) * 12 + ts.month
        season = 2.5 * np.sin(2 * np.pi * ts.month / 12)
        enso = 0.8 * np.sin(2 * np.pi * t / 45)
        lines.append(
            f"{ts.year:4d}{ts.month:5d}{24 + season + enso:9.2f}{enso:8.2f}"
            f"{26 + season / 2 + enso:9.2f}{enso:8.2f}"
            f"{28.5 + enso / 2:9.2f}{enso / 2:8.2f}"
            f"{27 + season / 3 + enso:9.2f}{enso:8.2f}"
        )
    return "\n".join(lines) + "\n"


def _hourly(start, end) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")


def _level(times: pd.DatetimeIndex, sid: str) -> np.ndarray:
    hours = (times - pd.Timestamp("2000-01-01", tz="UTC")) / pd.Timedelta(hours=1)
    hours = np.asarray(hours, dtype=float)
    return (1500 + int(sid) + 120 * np.sin(2 * np.pi * hours / (24 * 365.25))
            + 300 * np.sin(2 * np.pi * hours / 12.42)).round()


def _erddap_text(sid: str) -> str:
    times = _hourly("2012-01-01", FD_END)
    body = "\n".join(
        f"{int(v)},{t:%Y-%m-%dT%H:%M:%SZ}" for v, t in zip(_level(times, sid), times)
    )
    return "sea_level,time\nmillimeters,UTC\n" + body + "\n"


def _rapid_text(sid: str) -> str:
    """RAPID layout: the two months after FD, plus prediction-only rows."""
    times = _hourly(FD_END, _NOW)
    rows = [f"{t:%Y-%m-%d %H},{int(v) - 50},{int(v)}"
            for v, t in zip(_level(times, sid), times)]
    future = _hourly(_NOW + pd.DateOffset(days=10), _NOW + pd.DateOffset(days=11))
    rows += [f"{t:%Y-%m-%d %H},900," for t in future]
    return "Time,Prediction,Observation\n" + "\n".join(rows) + "\n"


class _FakeNetwork:
    """Answers every URL the pipeline requests and remembers which it saw."""

    def __init__(self):
        self.noaa = _noaa_text()
        self.cache: dict[str, str] = {}
        self.erddap_ids: list[str] = []
        self.rapid_ids: list[str] = []

    def get(self, url, timeout=None, **_):
        url = unquote(url)
        if url == download.NOAA_SST_URL:
            text = self.noaa
        elif url.startswith(download.ERDDAP_BASE):
            sid = re.search(r"uhslc_id=(\d+)", url).group(1)
            self.erddap_ids.append(sid)
            text = self.cache.setdefault("fd" + sid, _erddap_text(sid))
        elif "/stations/RAPID/" in url:
            sid = re.search(r"RAPID/(\d+)_", url).group(1)
            self.rapid_ids.append(sid)
            text = self.cache.setdefault("rp" + sid, _rapid_text(sid))
        else:
            raise AssertionError(f"unexpected URL requested: {url}")
        return SimpleNamespace(status_code=200, text=text,
                               raise_for_status=lambda: None)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_OLD_STAMP = "2000-01-01"


def _published(var_names) -> "OrderedDict[str, dict]":
    """An already-published page: every dataset ends in Dec 2001."""
    years = [2000] * 12 + [2001] * 12
    months = list(range(1, 13)) * 2
    return OrderedDict(
        (v, {"values": [1.0] * 24, "year": years, "month": months})
        for v in var_names
    )


def _prepare(uw, tmp_path, monkeypatch, argv_extra=()):
    net = _FakeNetwork()
    monkeypatch.setattr(download.requests, "get", net.get)
    # Raw copies go to data/input/ in the repo; keep the test hermetic.
    monkeypatch.setattr(download, "_save_raw", lambda *a, **k: None)
    download.clear_sst_cache()

    cfg = json.loads(json.dumps(REAL_CONFIG))
    cfg["sst"]["local_file"] = str(ROOT / REAL_CONFIG["sst"]["local_file"])
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    page = tmp_path / "phase_diagrams.html"
    page.write_text(
        "<html><script>\n"
        + uw._build_data_region(_published(uw.DATASETS), 10.0, 9.0, 5, 1975)
        + "\n</script>\n"
        '<p class="data-freshness"><!--DATA_FRESHNESS-->old<!--/DATA_FRESHNESS--></p>'
        "\n</html>\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    fresh = tmp_path / "freshness.json"
    prior = {
        "last_refreshed": _OLD_STAMP,
        "sst": {key: {"name": key, "last_success": _OLD_STAMP, "as_of": "2001-12",
                      "ok": True} for key, _ in uw._sst_indices(cfg)},
        "stations": {key: {"name": st["name"], "last_success": _OLD_STAMP,
                           "as_of": "2001-12", "ok": True}
                     for key, st in cfg["stations"].items()},
    }
    fresh.write_text(json.dumps(prior), encoding="utf-8")

    monkeypatch.setattr(uw, "HTML_FILES", [page])
    monkeypatch.setattr(uw, "OUT_DIR", out_dir)
    monkeypatch.setattr(uw, "FRESHNESS_FILE", fresh)
    monkeypatch.setattr(
        uw.sys, "argv",
        ["update_website.py", "--no-push", "--config", str(cfg_path), *argv_extra],
    )
    return net, cfg, page, out_dir, fresh


@pytest.fixture(autouse=True)
def _fresh_sst_cache():
    download.clear_sst_cache()
    yield
    download.clear_sst_cache()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_plain_run_processes_every_configured_dataset(tmp_path, monkeypatch, capsys):
    uw = _load_update_website()
    net, cfg, page, out_dir, fresh = _prepare(uw, tmp_path, monkeypatch)

    uw.main()   # no flags; must not exit

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    expected_last = f"{LAST_MONTH.year}-{LAST_MONTH.month:02d}"
    state = json.loads(fresh.read_text(encoding="utf-8"))

    # Every station in config.yaml was downloaded from ERDDAP and from RAPID.
    station_ids = sorted(st["id"] for st in cfg["stations"].values())
    assert sorted(set(net.erddap_ids)) == station_ids
    assert sorted(set(net.rapid_ids)) == station_ids

    # freshness.json: every SST index and every station moved forward.
    sst_keys = [key for key, _ in uw._sst_indices(cfg)]
    assert sst_keys[0] == "nino12" and {"nino3", "nino4", "nino34"} <= set(sst_keys)
    for key in sst_keys:
        entry = state["sst"][key]
        assert entry["last_success"] == today != _OLD_STAMP, key
        assert entry["ok"] is True and entry["as_of"] == expected_last, key
    for key in cfg["stations"]:
        entry = state["stations"][key]
        assert entry["last_success"] == today != _OLD_STAMP, key
        assert entry["ok"] is True, key
        assert entry["as_of"] == expected_last, (key, entry)
        assert entry["source"] == "FD+RAPID", key
    assert state["last_refreshed"] == today

    # Every dataset has a .dat file and a RAW_SERIES entry ending last month.
    html = page.read_text(encoding="utf-8")
    published = uw._extract_raw_series(html)
    for var_name, meta in uw.DATASETS.items():
        assert (out_dir / meta["dat"]).is_file(), meta["dat"]
        raw = published[var_name]
        assert (raw["year"][-1], raw["month"][-1]) == (
            LAST_MONTH.year, LAST_MONTH.month), var_name
    assert "Data last refreshed:" in html and ">old<" not in html

    # The summary table names every dataset with its source and status.
    out = capsys.readouterr().out
    assert "Update summary" in out
    for _, label in uw._sst_indices(cfg):
        assert re.search(rf"{re.escape(label)}\s+NOAA CPC\s+.*{expected_last}.*updated", out)
    for st in cfg["stations"].values():
        assert re.search(
            rf"{re.escape(st['name'])}\s+FD\+RAPID\s+\S+\s+{expected_last}\s+\d+\s+updated", out
        ), st["name"]


def test_sl_only_refreshes_stations_but_not_sst(tmp_path, monkeypatch):
    uw = _load_update_website()
    net, cfg, page, out_dir, fresh = _prepare(uw, tmp_path, monkeypatch,
                                              argv_extra=["--sl-only"])
    uw.main()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = json.loads(fresh.read_text(encoding="utf-8"))
    for key in cfg["stations"]:
        assert state["stations"][key]["last_success"] == today
    for key, _ in uw._sst_indices(cfg):
        assert state["sst"][key]["last_success"] == _OLD_STAMP
    # A partial run does not claim the whole site was refreshed.
    assert state["last_refreshed"] == _OLD_STAMP


def test_sst_only_refreshes_sst_but_not_stations(tmp_path, monkeypatch):
    uw = _load_update_website()
    net, cfg, page, out_dir, fresh = _prepare(uw, tmp_path, monkeypatch,
                                              argv_extra=["--sst-only"])
    uw.main()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = json.loads(fresh.read_text(encoding="utf-8"))
    assert net.erddap_ids == [] and net.rapid_ids == []
    for key, _ in uw._sst_indices(cfg):
        assert state["sst"][key]["last_success"] == today
    for key in cfg["stations"]:
        assert state["stations"][key]["last_success"] == _OLD_STAMP
    assert state["last_refreshed"] == _OLD_STAMP


def test_silent_skip_exits_nonzero_without_writing(tmp_path, monkeypatch, capsys):
    """If a configured station ends a run neither updated nor failed, abort."""
    uw = _load_update_website()
    net, cfg, page, out_dir, fresh = _prepare(uw, tmp_path, monkeypatch)
    before = page.read_text(encoding="utf-8")
    skipped_key, skipped = list(cfg["stations"].items())[-1]

    # Simulate the 2026-09 failure mode: a code path that never processes a
    # station and never records it. Its freshness entry is simply absent when
    # the guard runs.
    real_guard = uw._silently_skipped

    def guard_after_losing_station(cfg_, freshness, stamp, **kw):
        freshness["stations"].pop(skipped_key)
        return real_guard(cfg_, freshness, stamp, **kw)

    monkeypatch.setattr(uw, "_silently_skipped", guard_after_losing_station)
    with pytest.raises(SystemExit) as exc:
        uw.main()
    assert exc.value.code == 1
    assert page.read_text(encoding="utf-8") == before
    captured = capsys.readouterr()
    assert f"{skipped['name']} was neither updated nor recorded as failed" in captured.err
    assert "Update summary" in captured.out


def test_silently_skipped_rules():
    uw = _load_update_website()
    cfg = {"sst_indices": [{"key": "nino3", "label": "NINO3"}],
           "stations": {"callao": {"name": "Callao"}, "palau": {"name": "Palau"}}}
    stamp = "2026-10-03T06:00:00+00:00"
    state = {
        "sst": {"nino12": {"last_attempt": stamp, "ok": True},
                "nino3": {"last_attempt": stamp, "ok": True}},
        "stations": {
            # failed THIS run: handled
            "callao": {"last_attempt": stamp, "ok": False},
            # failed on an EARLIER run and untouched now: silently skipped
            "palau": {"last_attempt": "2026-09-05T06:00:00+00:00", "ok": False},
        },
    }
    assert uw._silently_skipped(cfg, state, stamp, sst=True, sl=True) == ["Palau"]
    assert uw._silently_skipped(cfg, state, stamp, sst=True, sl=False) == []
    del state["sst"]["nino12"]
    assert uw._silently_skipped(cfg, state, stamp, sst=True, sl=False) == ["NINO1+2"]


def test_config_station_missing_from_datasets_is_refused(tmp_path, monkeypatch, capsys):
    uw = _load_update_website()
    net, cfg, page, out_dir, fresh = _prepare(uw, tmp_path, monkeypatch)
    cfg["stations"]["nowhere"] = {"id": "999", "name": "Nowhere",
                                  "start_date": "2000-01-01"}
    cfg_path = Path(uw.sys.argv[3])
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        uw.main()
    assert exc.value.code == 1
    assert "station 'nowhere'" in capsys.readouterr().err


def test_workflow_flags_by_schedule():
    """The 5th runs everything (no flag); only the 18th passes --sl-only."""
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    crons = [s["cron"] for s in wf[True]["schedule"]]   # YAML 1.1: on -> True
    assert crons == ["0 6 5 * *", "0 6 18 * *"]

    script = next(step["run"] for step in wf["jobs"]["update"]["steps"]
                  if "update_website.py" in step.get("run", ""))
    assert 'FLAG=""' in script
    sl_branch = re.search(
        r'elif \[ "\$\{\{ github\.event\.schedule \}\}" = "([^"]+)" \]; then\s*'
        r'FLAG="([^"]+)"', script)
    assert sl_branch and sl_branch.groups() == ("0 6 18 * *", "--sl-only")
    # No other path sets a flag from the schedule.
    assert script.count("github.event.schedule") == 1
    assert "python scripts/update_website.py --no-push $FLAG" in script
