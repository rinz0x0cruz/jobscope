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