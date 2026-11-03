"""scripts/run_all.py: the SST output file must survive a second run."""

import importlib.util
import pathlib
from pathlib import Path

import numpy as np

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_all.py"


def _load_run_all():
    spec = importlib.util.spec_from_file_location("run_all", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_second_run_overwrites_the_dated_sst_file(tmp_path, monkeypatch):
    """Path.rename refuses to overwrite on Windows, so a rerun used to crash.

    The test gives rename its Windows behaviour on every platform, so it
    catches the bug in Linux CI too.
    """
    real_rename = pathlib.Path.rename

    def windows_rename(self, target):
        if Path(target).exists():
            raise FileExistsError(f"[WinError 183] {target}")
        return real_rename(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", windows_rename)

    ra = _load_run_all()
    run = {"n": 0}

    def fake_run_sst(output_file, **kwargs):
        run["n"] += 1
        Path(output_file).write_text(f"run {run['n']}\n", encoding="utf-8")
        return {"IYR": np.array([1975, 2026]), "MES": np.array([9, 8])}

    monkeypatch.setattr(ra.pipeline, "run_sst", fake_run_sst)
    cfg = {"sst": {"local_file": "unused", "ano_inicio": 1975},
           "filter": {"window": {}}}

    first = ra._run_sst(cfg, 10.0, 9.0, 5, tmp_path)
    second = ra._run_sst(cfg, 10.0, 9.0, 5, tmp_path)

    assert first["output_file"] == second["output_file"]
    assert Path(second["output_file"]).read_text(encoding="utf-8") == "run 2\n"
