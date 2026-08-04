"""Activation-readiness reporting: derivation, gating, and redaction.

Fixture databases and configurations only; no network, mailbox, or real secret.
"""
import copy
import json

import pytest

from jobscope.cli import readiness
from jobscope.core.config import DEFAULT_CONFIG
from jobscope.core.store import Store

_SECRET = "super-secret-app-password"  # pragma: allowlist secret
_ACCOUNT = "candidate.private@example.test"
_SENDER = "sender.private@example.test"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    # Build from DEFAULT_CONFIG so an ambient config.yaml cannot enable a lane.
    value = copy.deepcopy(DEFAULT_CONFIG)
    value["output"]["db_path"] = str(tmp_path / "readiness.db")
    return value


@pytest.fixture
def store(cfg):
    with Store(cfg["output"]["db_path"]) as handle:
        yield handle


def _lane(result, name):
    return next(item for item in result["lanes"] if item["lane"] == name)


def _enable_inbox(cfg, monkeypatch):
    cfg["inbox"].update({
        "enabled": True,
        "accounts": [{"email": _ACCOUNT, "password_env": "JOBSCOPE_TEST_INBOX_PW"}],  # pragma: allowlist secret
    })
    monkeypatch.setenv("JOBSCOPE_TEST_INBOX_PW", _SECRET)


def _enable_smtp(cfg, monkeypatch):
    cfg["email"].update({
        "enabled": True, "from_addr": _SENDER,
        "smtp_host": "smtp.example.test", "smtp_port": 587,
        "password_env": "JOBSCOPE_TEST_SMTP_PW",  # pragma: allowlist secret
    })
    monkeypatch.setenv("JOBSCOPE_TEST_SMTP_PW", _SECRET)


def test_all_disabled_configuration_is_healthy_and_exits_zero(cfg, store, capsys):
    assert readiness.run(cfg, store) == 0

    result = readiness.report(cfg, store)
    for name in ("inbox", "smtp", "outreach", "ai"):
        assert _lane(result, name)["state"] == "disabled"
        assert _lane(result, name)["blockers"] == []
    assert "DISABLED" in capsys.readouterr().out


@pytest.mark.parametrize("lane", readiness.LANES)
def test_every_lane_is_reported_with_a_known_state(cfg, store, lane):
    item = _lane(readiness.report(cfg, store), lane)

    assert item["state"] in {
        "disabled", "configured", "preflight_passed", "canary_passed", "active", "paused",
    }
    assert item["depends_on"] == list(readiness.DEPENDS[lane])
    assert "ai" not in item["depends_on"]


def test_retired_source_history_neither_enables_nor_blocks_discovery(cfg, store):
    # Retired-provider rows survive in source_health forever. Counting them
    # would make a dead lane look live and permanently unhealthy, because that
    # blocker could never clear.
    for status in ("saturated", "error", "ok"):
        store.set_source_health(
            f"jobspy:{status}", provider="jobspy", slug=status,
            status=status, item_count=0, attempts=1, status_code=0, detail="",
        )

    item = _lane(readiness.report(cfg, store), "discovery")

    assert item["enabled"] is False
    assert item["state"] == "disabled"
    assert item["blockers"] == []


@pytest.mark.parametrize("status,blocked", [
    ("ok", False), ("empty", False), ("partial", False),
    ("error", True), ("invalid", True), ("unsupported", True),
])
def test_only_reviewed_ats_sources_drive_discovery_health(cfg, store, status, blocked):
    cfg["search"]["companies"] = ["Acme|greenhouse|acme"]
    monitor = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="config",
    )
    store.set_source_health(
        f"monitor:{monitor['id']}", provider="greenhouse", slug="acme",
        status=status, item_count=3, attempts=1, status_code=200, detail="",
    )

    item = _lane(readiness.report(cfg, store), "discovery")

    assert item["enabled"] is True
    assert ("source_unhealthy" in item["blockers"]) is blocked


def test_a_retired_source_cannot_speak_for_the_discovery_lane(cfg, store):
    """`ats:` rows come from the deleted batch fetch. A live scan writes
    `monitor:<id>`, so a retired row must neither block the lane nor stand in for
    a runtime success."""
    cfg["search"]["companies"] = ["Acme|greenhouse|acme"]
    store.set_source_health(
        "ats:Acme", provider="greenhouse", slug="acme",
        status="error", item_count=0, attempts=1, status_code=500, detail="gone",
    )

    item = _lane(readiness.report(cfg, store), "discovery")

    assert item["blockers"] == []
    assert item["last_success_age_days"] is None


def test_missing_secret_blocks_by_reference_without_revealing_it(cfg, store, monkeypatch):
    _enable_inbox(cfg, monkeypatch)
    monkeypatch.delenv("JOBSCOPE_TEST_INBOX_PW", raising=False)
    monkeypatch.setattr(
        "jobscope.core.config._secret", lambda name, default="": default,
    )

    item = _lane(readiness.report(cfg, store), "inbox")

    assert item["state"] == "configured"
    assert "secret_unavailable" in item["blockers"]
    assert _SECRET not in json.dumps(item)


def test_canary_evidence_is_required_then_invalidated_by_drift(cfg, store, monkeypatch):
    _enable_smtp(cfg, monkeypatch)

    assert "canary_missing" in _lane(readiness.report(cfg, store), "smtp")["blockers"]

    readiness.record_canary(store, "smtp", cfg, result="passed")
    assert _lane(readiness.report(cfg, store), "smtp")["blockers"] == []

    cfg["email"]["smtp_host"] = "smtp.elsewhere.test"
    assert "canary_config_drift" in _lane(readiness.report(cfg, store), "smtp")["blockers"]


def test_failed_and_stale_canaries_invalidate_readiness(cfg, store, monkeypatch):
    _enable_inbox(cfg, monkeypatch)
    readiness.record_canary(store, "inbox", cfg, result="failed")

    assert "canary_failed" in _lane(readiness.report(cfg, store), "inbox")["blockers"]

    stale = json.loads(store.meta_get("readiness:canary:inbox"))
    stale["result"] = "passed"
    stale["at"] = "2020-01-01T00:00:00Z"
    store.meta_set("readiness:canary:inbox", json.dumps(stale))

    assert "canary_stale" in _lane(readiness.report(cfg, store), "inbox")["blockers"]

    store.meta_set("readiness:canary:inbox", "{not json")
    assert "canary_invalid" in _lane(readiness.report(cfg, store), "inbox")["blockers"]


def test_dependency_order_blocks_outreach_and_scheduler(cfg, store, monkeypatch):
    cfg["apply"]["outreach"]["enabled"] = True

    item = _lane(readiness.report(cfg, store), "outreach")

    assert "dependency_disabled:inbox" in item["blockers"]
    assert "dependency_disabled:smtp" in item["blockers"]
    assert readiness.run(cfg, store, require="outreach") == 1
    assert readiness.run(cfg, store, require="scheduler") == 1


def test_unresolved_delivery_pauses_outreach_and_blocks_activation(
    cfg, store, monkeypatch,
):
    _enable_inbox(cfg, monkeypatch)
    _enable_smtp(cfg, monkeypatch)
    cfg["apply"]["outreach"]["enabled"] = True
    campaign = store.create_outreach_campaign("Blocked", 1)
    target = store.upsert_outreach_campaign_target(campaign["id"], "Acme", "acme")
    store.conn.execute(
        "UPDATE outreach_campaign_targets SET error_code = 'delivery_unknown' WHERE id = ?",
        (target["id"],),
    )
    store.conn.commit()

    item = _lane(readiness.report(cfg, store), "outreach")

    assert item["state"] == "paused"
    assert "delivery_unknown" in item["blockers"]
    assert readiness.run(cfg, store, require="outreach") == 1


def test_require_returns_zero_only_with_current_evidence(cfg, store, monkeypatch):
    assert readiness.run(cfg, store, require="storage") == 0

    _enable_inbox(cfg, monkeypatch)
    assert readiness.run(cfg, store, require="inbox") == 1

    readiness.record_canary(store, "inbox", cfg, result="passed")
    assert readiness.run(cfg, store, require="inbox") == 0
    assert readiness.run(cfg, store, require="not-a-lane") == 2


def test_json_report_carries_the_documented_schema(cfg, store, capsys):
    assert readiness.run(cfg, store, as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)

    assert [item["lane"] for item in payload["lanes"]] == list(readiness.LANES)
    for item in payload["lanes"]:
        assert set(item) == {
            "lane", "state", "enabled", "blockers", "depends_on",
            "config_hash", "canary", "last_success_age_days",
        }
        assert len(item["config_hash"]) == 16


def test_report_never_emits_secrets_or_personal_data(cfg, store, monkeypatch, capsys):
    _enable_inbox(cfg, monkeypatch)
    _enable_smtp(cfg, monkeypatch)
    cfg["apply"]["outreach"]["enabled"] = True
    campaign = store.create_outreach_campaign("Private", 1)
    target = store.upsert_outreach_campaign_target(campaign["id"], "Private Co", "private co")
    store.set_outreach_campaign_draft(
        target["id"], selected_email="recruiter.private@example.test",
        subject="Private subject canary", body="Private body canary",
    )
    readiness.record_canary(store, "inbox", cfg, result="passed")
    readiness.record_canary(store, "smtp", cfg, result="passed")

    readiness.run(cfg, store)
    text = capsys.readouterr().out
    readiness.run(cfg, store, as_json=True)
    payload = capsys.readouterr().out

    for leak in (
        _SECRET, _ACCOUNT, _SENDER, "recruiter.private@example.test",
        "Private subject canary", "Private body canary", "JOBSCOPE_TEST_SMTP_PW",
    ):
        assert leak not in text
        assert leak not in payload


def test_reporting_performs_no_network_or_mutation(cfg, store, monkeypatch):
    _enable_inbox(cfg, monkeypatch)
    _enable_smtp(cfg, monkeypatch)

    def fail(*_args, **_kwargs):
        raise AssertionError("readiness reached the network")

    monkeypatch.setattr("jobscope.deliver.email.preflight", fail)
    monkeypatch.setattr("jobscope.ingest.inbox.run", fail)
    before = dict(store.conn.execute("SELECT key, value FROM meta").fetchall())

    readiness.run(cfg, store)

    assert dict(store.conn.execute("SELECT key, value FROM meta").fetchall()) == before


def test_canary_flag_records_evidence_from_a_non_sending_preflight(
    cfg, store, monkeypatch, capsys,
):
    _enable_smtp(cfg, monkeypatch)
    monkeypatch.setattr(
        "jobscope.deliver.email.preflight",
        lambda _cfg, **_kwargs: {"ok": True, "code": "ready"},
    )

    assert readiness.run(cfg, store, canary="smtp") == 0
    assert "smtp preflight: ready" in capsys.readouterr().out

    evidence = json.loads(store.meta_get("readiness:canary:smtp"))
    assert evidence["result"] == "passed"

    monkeypatch.setattr(
        "jobscope.deliver.email.preflight",
        lambda _cfg, **_kwargs: {"ok": False, "code": "auth_required"},
    )
    assert readiness.run(cfg, store, canary="smtp") == 1
    assert json.loads(store.meta_get("readiness:canary:smtp"))["result"] == "failed"
    assert readiness.run(cfg, store, canary="not-a-lane") == 2


def test_cli_lane_choices_match_the_module(tmp_path):
    from jobscope.cli import build_parser

    parser = build_parser()
    action = next(
        item for item in parser._subparsers._group_actions[0].choices["readiness"]._actions
        if item.dest == "require"
    )

    assert tuple(name for name in action.choices if name) == readiness.LANES


def test_a_malformed_account_entry_is_reported_rather_than_crashing(cfg, store):
    # A plausible hand-edit: a plain list of addresses instead of mappings.
    cfg["inbox"].update({
        "enabled": True, "accounts": [_ACCOUNT, None, 42, {"email": "", "password_env": ""}],
    })

    item = _lane(readiness.report(cfg, store), "inbox")

    assert "account_incomplete" in item["blockers"]
    assert item["state"] == "configured"
    assert _ACCOUNT not in json.dumps(item)


def test_unparseable_stored_timestamps_never_crash_the_report(cfg, store):
    store.meta_set("campaign:replies:last_checked_at", "not-a-date")
    store.meta_set("refresh:last_date", "\x00garbage")

    result = readiness.report(cfg, store)

    assert _lane(result, "storage")["last_success_age_days"] is None
    assert _lane(result, "scheduler")["last_success_age_days"] is None


def test_a_canary_usage_error_never_becomes_recorded_evidence(cfg, store, monkeypatch):
    _enable_inbox(cfg, monkeypatch)

    # Forgetting --account, or naming an address that is not configured, says
    # nothing about the mailbox and must not poison readiness.
    assert readiness.run(cfg, store, canary="inbox", account="") == 2
    assert store.meta_get("readiness:canary:inbox", "") == ""

    assert readiness.run(cfg, store, canary="inbox", account="nobody@example.test") == 2
    assert store.meta_get("readiness:canary:inbox", "") == ""


def test_a_genuine_canary_failure_is_recorded_as_evidence(cfg, store, monkeypatch):
    _enable_inbox(cfg, monkeypatch)

    def failing(*_args, **_kwargs):
        raise RuntimeError("inbox canary wrote mail events")

    monkeypatch.setattr("jobscope.cli.inbox_canary.run", failing)

    assert readiness.run(cfg, store, canary="inbox", account=_ACCOUNT) == 1
    assert json.loads(store.meta_get("readiness:canary:inbox"))["result"] == "failed"
    assert "canary_failed" in _lane(readiness.report(cfg, store), "inbox")["blockers"]
