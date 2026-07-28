"""Monitored-only scan routing tests; no network or optional scraper package."""
import builtins
import os

import pytest

from jobscope.core.config import load_config
from jobscope.core.store import Store
from jobscope.ingest import monitor, scrape


def _cfg(tmp_path):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.fspath(tmp_path / "scan.db")
    return cfg


def _summary():
    return {
        "companies": 1, "successful": 1, "matched": 2, "new": 1,
    }


@pytest.mark.parametrize("mode", ["all", "monitored"])
def test_scan_uses_only_monitored_adapters_without_jobspy(tmp_path, monkeypatch, mode):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "jobspy" or name.startswith("jobspy."):
            pytest.fail("monitored scan attempted to import JobSpy")
        return original_import(name, *args, **kwargs)

    calls = []
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(
        monitor, "scan_active_monitors",
        lambda cfg, store: calls.append((cfg, store)) or _summary(),
    )
    cfg = _cfg(tmp_path)
    with Store(cfg["output"]["db_path"]) as store:
        assert scrape.run(cfg, store, mode=mode) == 0

    assert len(calls) == 1


def test_broad_discovery_mode_is_rejected(tmp_path):
    cfg = _cfg(tmp_path)
    with Store(cfg["output"]["db_path"]) as store:
        with pytest.raises(ValueError, match="invalid scan mode"):
            scrape.run(cfg, store, mode="discovery")