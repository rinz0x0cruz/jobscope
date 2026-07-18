"""Golden evaluation for deterministic company-board match decisions.

The corpus captures the NTT false-negative incident plus senior/contextual
negatives. It is key-free and network-free so precision/recall regressions block CI.
"""
import json
from pathlib import Path

from jobscope.analyze import profile
from jobscope.analyze.review import score_jobs
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store
from jobscope.ingest import ats

FIXTURES = Path(__file__).parent / "fixtures" / "match_decision_eval.jsonl"


def _cases():
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            yield json.loads(line)


def _resume() -> Resume:
    return Resume(
        full_name="Candidate",
        location="Punjab, India",
        titles=["Security Researcher Intern"],
        seniority="junior",
        years_experience=1.2,
        skills=[
            "Cyber Threat Intelligence", "threat hunting", "SIEM",
            "incident response", "linux", "malware analysis",
            "vulnerability management", "NIST", "python",
        ],
    )


def _reason(cfg: dict, store, job: Job) -> tuple[bool, str]:
    candidates, funnel = ats.filter_profile_jobs_with_funnel(cfg, store, [job])
    if not funnel["geo_eligible"]:
        return False, "geography"
    if not funnel["title_eligible"]:
        return False, "title"
    scored = score_jobs(cfg, store, candidates)[0]
    if scored.tier != "Skip":
        return True, "matched"
    if scored.rationale.startswith("needs ~"):
        return False, "experience_cap"
    if " | top:" in scored.rationale:
        return False, "other_filter"
    return False, "below_threshold"


def test_match_decision_golden_corpus(tmp_path):
    cfg = load_config(None)
    cfg["output"]["db_path"] = str(tmp_path / "eval.db")
    cfg["filters"]["max_years_experience"] = 2
    resume = _resume()
    cases = list(_cases())
    assert cases, "match decision golden set is empty"

    with Store(cfg["output"]["db_path"]) as store:
        store.save_resume(resume, name="research")
        profile.write_profile(
            profile._profile_file(cfg, "research"),
            {
                **profile.build_profile(resume, cfg, "research"),
                "search_terms": [
                    "Security Researcher", "Threat Hunter", "Detection Engineer",
                    "Malware Analyst", "Incident Response Analyst", "Security Engineer",
                ],
                "locations": ["Remote", "India"],
            },
        )
        profile.set_active(cfg, "research")

        outcomes = {}
        for case in cases:
            job = Job(
                id=case["id"], source="golden", company="NTT DATA",
                title=case["title"], location=case["location"],
                is_remote="remote" in case["location"].lower(),
                url=f"https://example.test/{case['id']}",
                description=case["description"], date_posted=case["date_posted"],
            )
            outcomes[case["id"]] = _reason(cfg, store, job)

    true_positive = false_positive = true_negative = false_negative = 0
    for case in cases:
        predicted, reason = outcomes[case["id"]]
        expected = bool(case["expected_match"])
        assert reason == case["expected_reason"], case["id"]
        true_positive += int(predicted and expected)
        false_positive += int(predicted and not expected)
        true_negative += int(not predicted and not expected)
        false_negative += int(not predicted and expected)

    assert {
        "tp": true_positive,
        "fp": false_positive,
        "tn": true_negative,
        "fn": false_negative,
    } == {"tp": 4, "fp": 0, "tn": 6, "fn": 0}