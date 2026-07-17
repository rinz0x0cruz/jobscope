from pathlib import Path


def test_mutation_dispatch_skips_unrelated_network_pipeline():
    workflow = Path(".github/workflows/refresh.yml").read_text(encoding="utf-8")

    assert 'if [ -n "$JOBSCOPE_MUTATIONS_JSON" ]; then' in workflow
    assert 'python -m jobscope companies apply --actions-file data/monitoring-actions.json' in workflow
    assert 'else\n            python -m jobscope companies scan' in workflow
    assert 'python -m jobscope outreach-scan || echo "::warning::outreach scan failed (non-fatal)"\n          fi' in workflow