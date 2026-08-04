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

    # Only read-only workflows may keep a GitHub schedule: the ATS canary probes
    # public boards, and the dependency audit installs and inspects the lock.
    assert scheduled == ["ats-canary.yml", "deps-audit.yml"]


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