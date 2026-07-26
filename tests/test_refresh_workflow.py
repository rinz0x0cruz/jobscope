import re
import textwrap
from pathlib import Path

import yaml


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


def test_hosted_workflow_python_heredocs_compile():
    for workflow_path in (
        Path(".github/workflows/hosted-ops.yml"),
        Path(".github/workflows/hosted-publish.yml"),
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