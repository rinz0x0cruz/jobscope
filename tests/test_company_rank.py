from datetime import datetime, timezone

import pytest

from jobscope.apply.company_rank import is_security_role, rank_companies
from jobscope.core.model import Application, Job
from jobscope.core.store import Store


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    value = Store(str(tmp_path / "ranking.db"))
    yield value
    value.close()


def _job(company: str, location: str, *, salary: float = 0, remote: bool = False,
         scope: str = "") -> Job:
    return Job(
        source="test", title="Cloud Security Engineer", company=company,
        location=location, is_remote=remote, remote_scope=scope,
        url=f"https://jobs.example/{company.lower().replace(' ', '-')}",
        salary_max=salary or None, salary_interval="yearly", currency="INR",
        date_posted="2026-07-10",
    ).ensure_id()


@pytest.mark.parametrize(("title", "tier", "expected"), [
    ("Security Analyst", "Good", True),
    ("Manager - Cybersecurity", "Stretch", True),
    ("Audit and Vulnerability Management Analyst II", "Stretch", True),
    ("Staff Backend Engineer, Software Supply Chain Security", "Good", True),
    ("Application Security Intern", "Good", True),
    ("Security Guard", "Stretch", False),
    ("International Consultant on Minerals Crime and Security of Supply Chains", "Stretch", False),
    ("Intermediate Backend Engineer", "Good", False),
    ("Security Analyst", "Skip", False),
])
def test_security_role_requires_cyber_title_and_profile_fit(title, tier, expected):
    job = Job(title=title, tier=tier, description="Reduce security and compliance risk.")
    assert is_security_role(job) is expected


def test_rank_companies_hard_gates_region_and_routes_application_history(store):
    india = _job("Acme Security", "Bengaluru, India", salary=3_000_000)
    foreign = _job("Foreign Security", "San Francisco, United States", salary=9_000_000)
    applied = _job("Applied Security", "Pune, India", salary=4_000_000)
    for job in (india, foreign, applied):
        store.upsert_job(job)
    store.set_application(Application(job_id=applied.id, status="applied"))

    result = rank_companies(
        {}, store, 5,
        candidates=["Acme Security", "Acme Security Ltd", "Foreign Security", "Applied Security"],
        now=NOW,
    )

    assert [item["company"] for item in result["ranked"]] == ["Acme Security"]
    assert result["ranked"][0]["factors"] == {
        "region": 1.0, "compensation": 0.75, "growth": 0.73,
    }
    assert result["ranked"][0]["evidence_coverage"] == 0.92
    assert result["ranked"][0]["score"] == 86.3
    assert result["ranked"][0]["evidence"]["compensation_basis"] == "structured"
    assert result["follow_up"][0]["company"] == "Applied Security"
    assert any(item["company"] == "Foreign Security" and
               item["reason"] == "insufficient_india_evidence"
               for item in result["blocked"])


def test_rank_companies_accepts_auditable_factor_overrides(store):
    cfg = {
        "apply": {"outreach": {"campaign": {"company_overrides": {
            "New Cyber": {
                "india_relevance": 0.8,
                "india_evidence": "India security team",
                "compensation": 0.9,
                "compensation_evidence": "Published India salary band",
                "growth": 0.7,
                "growth_evidence": "Expanded Bengaluru team",
            },
        }}}},
    }

    result = rank_companies(cfg, store, 1, candidates=["New Cyber"], now=NOW)

    assert result["ranked"][0]["score"] == 81.0
    assert result["ranked"][0]["evidence_coverage"] == 1.0
    assert result["ranked"][0]["evidence"]["region"] == ["India security team"]


def test_rank_companies_rejects_invalid_weights(store):
    try:
        rank_companies({}, store, 1, candidates=["Acme"],
                       weights={"region": 1, "compensation": 1, "growth": 1}, now=NOW)
    except ValueError as error:
        assert "sum to 1" in str(error)
    else:
        raise AssertionError("invalid weights were accepted")


def test_rank_companies_rejects_backend_roles_with_security_boilerplate(store):
    backend = _job("GitLab", "Remote, India")
    backend.title = "Intermediate Backend Engineer, Tenant Scale"
    backend.description = (
        "Our DevSecOps platform improves productivity and reduces security and compliance risk."
    )
    backend.tier = "Skip"
    store.upsert_job(backend)

    result = rank_companies({}, store, 1, candidates=["GitLab"], now=NOW)

    assert result["ranked"] == []
    assert result["blocked"] == [{
        "company": "GitLab", "company_key": "gitlab",
        "reason": "insufficient_india_evidence", "region_score": 0.0,
    }]


def test_rank_companies_uses_only_non_skip_security_titles(store):
    backend = _job("Acme", "Remote, India", salary=8_000_000)
    backend.title = "Senior Backend Engineer"
    backend.description = "Build a security platform."
    backend.tier = "Skip"
    security = _job("Acme", "Pune, India", salary=3_000_000)
    security.title = "Cloud Security Engineer"
    security.tier = "Good"
    security.url += "/security"
    security.id = ""
    security.ensure_id()
    store.upsert_job(backend)
    store.upsert_job(security)

    result = rank_companies({}, store, 1, candidates=["Acme"], now=NOW)

    target = result["ranked"][0]
    assert target["evidence"]["region"] == ["Cloud Security Engineer — Pune, India"]
    assert target["evidence"]["compensation"][0] == (
        "Median structured maximum: 3,000,000 INR/year"
    )