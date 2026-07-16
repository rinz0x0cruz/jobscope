from jobscope.cli import doctor
from jobscope.core.config import load_config
from jobscope.core.store import Store


def _cfg(tmp_path):
    cfg = load_config("__no_such_config_for_tests__.yaml")
    cfg["output"]["db_path"] = str(tmp_path / "jobscope.db")
    return cfg


def test_doctor_accepts_healthy_offline_setup(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()

    checks = doctor.inspect(
        cfg, which=lambda _name: "available", publish_ready=lambda: True)

    assert not [check for check in checks if check.level == "error"]
    assert any(check.name == "database" and check.level == "ok" for check in checks)


def test_doctor_reports_missing_or_corrupt_database(tmp_path):
    cfg = _cfg(tmp_path)
    missing = doctor.inspect(cfg, which=lambda _name: None)
    assert any(check.name == "database" and check.level == "error" for check in missing)

    path = tmp_path / "jobscope.db"
    path.write_bytes(b"not sqlite")
    corrupt = doctor.inspect(cfg, which=lambda _name: None)
    assert any("not a SQLite database" in check.detail for check in corrupt)


def test_doctor_reports_missing_required_inbox_secret(tmp_path):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()
    cfg["inbox"]["enabled"] = True
    cfg["inbox"]["accounts"] = [{
        "email": "me@example.com", "password_env": "MISSING_PASSWORD",  # pragma: allowlist secret
    }]

    checks = doctor.inspect(
        cfg, secret_lookup=lambda _cfg, _account: "", which=lambda _name: "available")

    assert any(
        check.name == "inbox" and check.level == "error"
        and "MISSING_PASSWORD" in check.detail for check in checks)


def test_doctor_requires_publish_passphrase_when_refresh_is_enabled(tmp_path):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()

    checks = doctor.inspect(
        cfg, which=lambda _name: "available", publish_ready=lambda: False)

    assert any(check.name == "publish" and check.level == "error" for check in checks)


def test_doctor_warns_on_unhealthy_source_and_refresh_failure(tmp_path):
    cfg = _cfg(tmp_path)
    with Store(cfg["output"]["db_path"]) as store:
        store.set_source_health(
            "ats:Acme", provider="greenhouse", slug="acme", status="error",
            detail="HTTP 503",
        )
        store.meta_set("refresh:last_failure", "2026-07-15T00:00:00")
        store.meta_set("refresh:last_failed_stage", "publish")

    checks = doctor.inspect(cfg, which=lambda _name: "available")

    assert any(check.name == "sources" and check.level == "warn" for check in checks)
    assert any(
        check.name == "refresh" and check.level == "warn" and "publish" in check.detail
        for check in checks)


def test_doctor_reports_unresolved_company_monitors(tmp_path):
    cfg = _cfg(tmp_path)
    with Store(cfg["output"]["db_path"]) as store:
        store.upsert_company_monitor("Unknown Labs", added_from="application")

    checks = doctor.inspect(cfg, which=lambda _name: "available", publish_ready=lambda: True)

    assert any(
        check.name == "companies" and check.level == "warn"
        and "Unknown Labs" in check.detail for check in checks
    )