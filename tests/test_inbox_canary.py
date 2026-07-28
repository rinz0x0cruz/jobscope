from pathlib import Path

import pytest

from jobscope.cli import inbox_canary
from jobscope.core.config import load_config


def _cfg():
    cfg = load_config("__missing_canary_config__.yaml")
    cfg["inbox"]["enabled"] = True
    cfg["inbox"]["accounts"] = [{
        "email": "canary@example.com",
        "password_env": "JOBSCOPE_CANARY_PASSWORD",  # pragma: allowlist secret
    }]
    cfg["inbox"]["store_snippets"] = True
    cfg["email"]["enabled"] = True
    cfg["ai"]["enabled"] = True
    cfg["apply"]["outreach"]["enabled"] = True
    return cfg


def test_canary_forces_dry_run_and_deletes_isolated_database(tmp_path):
    seen = {}

    class TempDirectory:
        def __init__(self, **_kwargs):
            self.path = tmp_path / "isolated"
            self.path.mkdir()

        def __enter__(self):
            return str(self.path)

        def __exit__(self, *_args):
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    def sync(cfg, store, **kwargs):
        seen.update(cfg=cfg, kwargs=kwargs, db_path=store.path)
        store.set_source_health(
            "inbox:canary@example.com", provider="imap",
            slug="canary@example.com", status="ok", item_count=1,
        )
        return 0

    assert inbox_canary.run(
        _cfg(), "canary@example.com", sync=sync,
        temp_dir_factory=TempDirectory,
    ) == 0

    assert seen["kwargs"] == {
        "dry_run": True,
        "account": "canary@example.com",
        "backfill": False,
        "initiator": "cli",
    }
    assert seen["cfg"]["inbox"]["store_snippets"] is False
    assert seen["cfg"]["inbox"]["include_spam"] is False
    assert seen["cfg"]["email"]["enabled"] is False
    assert seen["cfg"]["ai"]["enabled"] is False
    assert seen["cfg"]["apply"]["outreach"]["enabled"] is False
    assert not Path(seen["db_path"]).exists()
    assert not (tmp_path / "isolated").exists()


def test_canary_rejects_unknown_or_ambiguous_account():
    cfg = _cfg()
    with pytest.raises(ValueError, match="match exactly one"):
        inbox_canary.run(cfg, "missing@example.com")
    cfg["inbox"]["accounts"].append(dict(cfg["inbox"]["accounts"][0]))
    with pytest.raises(ValueError, match="match exactly one"):
        inbox_canary.run(cfg, "canary@example.com")


def test_canary_fails_if_sync_writes_events_or_markers(tmp_path):
    def writes_event(_cfg, store, **_kwargs):
        store.meta_set("inbox:canary@example.com:last_uid", "1")
        return 0

    with pytest.raises(RuntimeError, match="UID markers"):
        inbox_canary.run(_cfg(), "canary@example.com", sync=writes_event)


def test_canary_requires_one_classified_message():
    with pytest.raises(RuntimeError, match="expected benign message"):
        inbox_canary.run(_cfg(), "canary@example.com", sync=lambda *_args, **_kwargs: 0)