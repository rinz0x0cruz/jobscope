import ast
from pathlib import Path

import pytest
import yaml

from jobscope.cli import build_parser
from jobscope.core.config import DEFAULT_CONFIG
from jobscope.ingest import ats

ROOT = Path(__file__).resolve().parents[1]
ACQUISITION_FILES = (
    ROOT / "jobscope" / "ingest" / "ats.py",
    ROOT / "jobscope" / "ingest" / "ats_canary.py",
    ROOT / "jobscope" / "ingest" / "monitor.py",
    ROOT / "jobscope" / "ingest" / "scrape.py",
)
BROAD_SEARCH_KEYS = {
    "sites", "google_term", "results_wanted", "hours_old", "distance",
    "linkedin_fetch_description", "proxies",
}


def test_automatic_sources_are_exact_reviewed_provider_host_pairs():
    assert ats.SUPPORTED_PROVIDERS == frozenset({"greenhouse", "lever", "ashby"})
    assert ats.AUTOMATIC_SOURCE_HOSTS == {
        "greenhouse": frozenset({"boards-api.greenhouse.io"}),
        "lever": frozenset({"api.lever.co"}),
        "ashby": frozenset({"api.ashbyhq.com"}),
    }


def test_defaults_and_example_have_no_broad_discovery_or_proxy_controls():
    example = yaml.safe_load((ROOT / "config.example.yaml").read_text("utf-8"))

    assert "discovery" not in DEFAULT_CONFIG
    assert "discovery" not in example
    assert BROAD_SEARCH_KEYS.isdisjoint(DEFAULT_CONFIG["search"])
    assert BROAD_SEARCH_KEYS.isdisjoint(example["search"])


def test_acquisition_code_has_no_scraper_evasion_or_impersonation_mechanisms():
    forbidden = (
        "python-jobspy", "from jobspy", "import jobspy", "tls-client", "tls_client",
        "cloudscraper", "undetected_chromedriver", "captcha", "proxy_rotation",
        "proxy-rotation", "impersonate=", "browserforge", "linkedin_fetch_description",
    )
    violations = []
    for path in ACQUISITION_FILES:
        text = path.read_text("utf-8").lower()
        for needle in forbidden:
            if needle in text:
                violations.append(f"{path.relative_to(ROOT)}: {needle}")

    assert violations == []


def test_dependency_graph_has_no_retired_scraper_footprint():
    dependency_text = "\n".join(
        (ROOT / name).read_text("utf-8").lower()
        for name in ("pyproject.toml", "requirements.txt", "requirements.lock")
    )
    for package in (
        "python-jobspy", "tls-client", "markdownify", "pydantic-core",
        "typing-inspection",
    ):
        assert package not in dependency_text


def test_workflows_have_no_retired_discovery_switch_or_invocation():
    workflow_text = "\n".join(
        path.read_text("utf-8").lower()
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    for needle in ("force-discovery", "--mode discovery", "full_scan"):
        assert needle not in workflow_text


@pytest.mark.parametrize(
    "argv",
    [
        ["scan", "--mode", "discovery"],
        ["scan", "--force-discovery"],
        ["refresh", "--full-scan"],
    ],
)
def test_cli_rejects_retired_discovery_controls(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_assisted_apply_has_no_browser_submission_action():
    tree = ast.parse((ROOT / "jobscope" / "apply" / "apply.py").read_text("utf-8"))
    invoked_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert {"click", "press", "submit"}.isdisjoint(invoked_attributes)