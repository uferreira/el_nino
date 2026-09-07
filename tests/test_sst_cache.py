"""Regression tests for the in-process SST download cache."""

import numpy as np
import pytest

from el_nino import download


@pytest.fixture(autouse=True)
def _clean_cache():
    """Every test starts and ends with an empty cache."""
    download.clear_sst_cache()
    yield
    download.clear_sst_cache()


def _fake_record():
    return {
        "IYR": np.array([2000, 2000], dtype=np.int32),
        "MES": np.array([1, 2], dtype=np.int32),
        "SST0": np.array([25.0, 26.0], dtype=np.float64),
    }


def test_repeated_loads_download_once(monkeypatch):
    """Four index pipelines must trigger a single NOAA download."""
    calls = []

    def _spy(local_file, ano_inicio):
        calls.append((local_file, ano_inicio))
        return _fake_record()

    monkeypatch.setattr(download, "_load_sst_uncached", _spy)

    for _ in range(4):
        rec = download.load_sst(local_file="hist.txt", ano_inicio=1975)
        assert rec["SST0"].tolist() == [25.0, 26.0]

    assert calls == [("hist.txt", 1975)]


def test_cache_hands_out_independent_copies(monkeypatch):
    """In-place work by one caller must not reach the next one."""
    monkeypatch.setattr(
        download, "_load_sst_uncached", lambda local_file, ano_inicio: _fake_record()
    )

    first = download.load_sst(local_file="hist.txt", ano_inicio=1975)
    first["SST0"] *= 0.0

    second = download.load_sst(local_file="hist.txt", ano_inicio=1975)
    assert second["SST0"].tolist() == [25.0, 26.0]
    assert second["SST0"] is not first["SST0"]


def test_distinct_arguments_are_cached_separately(monkeypatch):
    """A different start year is a different record, not a cache hit."""
    calls = []
    monkeypatch.setattr(
        download,
        "_load_sst_uncached",
        lambda local_file, ano_inicio: calls.append(ano_inicio) or _fake_record(),
    )

    download.load_sst(local_file="hist.txt", ano_inicio=1975)
    download.load_sst(local_file="hist.txt", ano_inicio=1950)
    download.load_sst(local_file="hist.txt", ano_inicio=1975)

    assert calls == [1975, 1950]


def test_use_cache_false_forces_a_fresh_download(monkeypatch):
    """The escape hatch re-downloads and refreshes the cached entry."""
    calls = []
    monkeypatch.setattr(
        download,
        "_load_sst_uncached",
        lambda local_file, ano_inicio: calls.append(ano_inicio) or _fake_record(),
    )

    download.load_sst(local_file="hist.txt", ano_inicio=1975)
    download.load_sst(local_file="hist.txt", ano_inicio=1975, use_cache=False)

    assert calls == [1975, 1975]
