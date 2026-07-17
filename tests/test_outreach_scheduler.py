import json
from pathlib import Path

from jobscope.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_campaign_readiness_accepts_resolved_secret(tmp_path, monkeypatch, capsys):
    config = tmp_path / "scheduler.json"
    config.write_text(json.dumps({
        "apply": {"outreach": {"enabled": True}},
        "email": {
            "enabled": True,
            "from_addr": "jane@example.com",
        },
    }), encoding="utf-8")
    monkeypatch.setattr("jobscope.core.config.smtp_password", lambda _cfg: str(tmp_path))

    assert main(["--config", str(config), "campaign", "ready"]) == 0
    assert "scheduler ready" in capsys.readouterr().out


def test_outreach_task_is_single_instance_and_cannot_force_send():
    register = (ROOT / "scripts" / "register-outreach-task.ps1").read_text(encoding="utf-8")
    unregister = (ROOT / "scripts" / "unregister-outreach-task.ps1").read_text(encoding="utf-8")

    assert "campaign tick" in register
    assert "campaign ready" in register
    assert "MultipleInstances IgnoreNew" in register
    assert "RepetitionInterval" in register
    assert "--force" not in register
    assert "Unregister-ScheduledTask" in unregister