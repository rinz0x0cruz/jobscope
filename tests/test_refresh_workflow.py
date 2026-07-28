import json
import re
import textwrap
from pathlib import Path

import yaml

_MUTATING = ("/api/automation/refresh", "/api/automation/tick", "python -m jobscope refresh")


def _triggers(text):
    # YAML 1.1 parses a bare `on:` key as the boolean True.
    parsed = yaml.safe_load(text)
    value = parsed.get(True, parsed.get("on"))
    return value if isinstance(value, dict) else {}


def test_the_legacy_refresh_schedule_is_removed_from_source():
    text = Path(".github/workflows/refresh.yml").read_text(encoding="utf-8")
    triggers = _triggers(text)

    assert "schedule" not in triggers
    assert "workflow_dispatch" in triggers


def test_no_github_workflow_schedules_a_mutating_run():
    scheduled = []
    for path in sorted(Path(".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "schedule" not in _triggers(text):
            continue
        scheduled.append(path.name)
        for marker in _MUTATING:
            assert marker not in text, f"{path.name} schedules mutating work"

    # Only the read-only ATS canary may keep a GitHub schedule.
    assert scheduled == ["ats-canary.yml"]


def test_only_the_allowlisted_worker_crons_can_become_the_writer():
    config = json.loads(re.sub(
        r"^\s*//.*$", "",
        Path("cloudflare/automation-wrangler.jsonc").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    ))
    worker = Path("cloudflare/automation-worker.mjs").read_text(encoding="utf-8")
    allowlist = set(re.findall(r"\['([^']+)', \{ path:", worker))

    assert allowlist == {"17 */3 * * *", "*/30 * * * *"}
    # Empty until every activation canary passes; any future entry must be one
    # the worker already recognizes, or the slot is rejected at runtime.
    assert set(config["triggers"]["crons"]) <= allowlist
    assert config["vars"]["AUTOMATION_MODE"] == "observe"


def test_mutation_dispatch_skips_unrelated_network_pipeline():
    workflow = yaml.safe_load(Path(".github/workflows/refresh.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["refresh"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Sync inbox + rescore (AI off)")
    lines = script.splitlines()
    else_index = next(index for index, line in enumerate(lines) if line.strip() == "else")
    mutation_branch = "\n".join(lines[:else_index])
    full_refresh_branch = "\n".join(lines[else_index + 1:])

    assert 'if [ -n "$JOBSCOPE_MUTATIONS_JSON" ]; then' in mutation_branch
    assert 'python -m jobscope companies apply --actions-file data/monitoring-actions.json' in mutation_branch
    assert "python -m jobscope companies scan" not in mutation_branch
    assert "python -m jobscope companies scan" in full_refresh_branch
    assert "python -m jobscope inbox --reclassify" in full_refresh_branch
    assert "python -m jobscope outreach-scan" in full_refresh_branch


def test_hosted_operations_stay_manual_scoped_and_redacted():
    text = Path(".github/workflows/hosted-ops.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert "workflow_dispatch:" in text and "schedule:" not in text
    assert workflow["concurrency"] == {
        "group": "jobscope-hosted-operations", "cancel-in-progress": False,
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert "/api/automation/refresh" in text
    assert "/api/automation/status" in text
    assert "/api/automation/tick" in text
    assert "/api/campaigns/action" not in text
    assert "PRIVATE" not in text


def test_hosted_publish_reuses_verified_external_payload_path():
    text = Path(".github/workflows/hosted-publish.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert "workflow_dispatch:" in text and "schedule:" not in text
    assert workflow["concurrency"]["group"] == "jobscope-hosted-operations"
    assert workflow["permissions"] == {"contents": "write"}
    assert "/api/automation/snapshot" in text
    assert "JOBSCOPE_PUBLISH_ENCRYPTED_JSON" in text
    assert "scripts/publish.sh --encrypted --force" in text
    assert "JOBSCOPE_APPS_PASSPHRASE" not in text


def test_hosted_full_backup_is_manual_encrypted_and_off_provider():
    text = Path(".github/workflows/hosted-backup.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert "workflow_dispatch:" in text and "schedule:" not in text
    assert workflow["concurrency"]["group"] == "jobscope-hosted-operations"
    assert workflow["permissions"] == {"contents": "read"}
    assert "/api/automation/backup" in text
    assert "/api/automation/backup/ack" in text
    assert "jobscope.core.backup verify" in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text
    assert "jobscope.db.jsdb" in text
    assert "jobscope.db\n" not in text


def test_restore_drill_uses_selected_backup_and_pulled_digest_without_outbound_effects():
    text = Path(".github/workflows/hosted-restore-drill.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert "workflow_dispatch:" in text and "schedule:" not in text
    assert workflow["permissions"] == {
        "actions": "read", "contents": "read", "packages": "read",
    }
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in text
    assert '"$repository@$DIGEST"' in text
    assert "jobscope.core.backup restore" in text
    assert "JOBSCOPE_RECOVERY_MODE=1" in text
    assert "python -m jobscope --config /data/config.yaml doctor" in text
    assert "/api/automation/snapshot" in text
    assert "/api/automation/tick" in text
    assert "recovery_mode" in text
    assert "docker restart" in text


def test_hosted_workflow_python_heredocs_compile():
    for workflow_path in (
        Path(".github/workflows/hosted-ops.yml"),
        Path(".github/workflows/hosted-publish.yml"),
        Path(".github/workflows/hosted-backup.yml"),
        Path(".github/workflows/hosted-restore-drill.yml"),
    ):
        text = workflow_path.read_text(encoding="utf-8")
        blocks = re.findall(r"<<'PY'\n(.*?)\n\s*PY(?:\n|$)", text, re.DOTALL)
        assert blocks, f"no Python heredoc found in {workflow_path}"
        for index, block in enumerate(blocks, start=1):
            compile(
                textwrap.dedent(block),
                f"{workflow_path}:python-heredoc-{index}",
                "exec",
            )