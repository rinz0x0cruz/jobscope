import os

from jobscope.resume import parse_resume

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "resume.md")


def test_parse_markdown_resume_contact():
    r = parse_resume(FIX)
    assert r.full_name == "Jane Doe"
    assert r.email == "jane.doe@example.com"
    assert "linkedin" in r.links and "github" in r.links


def test_parse_markdown_resume_skills():
    r = parse_resume(FIX)
    low = [s.lower() for s in r.skills]
    for expected in ("python", "aws", "kubernetes", "threat modeling", "iam"):
        assert expected in low, f"missing skill {expected} in {low}"


def test_parse_markdown_seniority_and_years():
    r = parse_resume(FIX)
    assert r.seniority == "senior"
    assert r.years_experience >= 6  # 2016 -> present
