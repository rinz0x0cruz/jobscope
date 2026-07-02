"""Tests for experience-requirement detection and the max-years-experience filter."""
from jobscope.match import apply_filters, required_experience_years
from jobscope.model import Job


def _job(title, desc=""):
    return Job(title=title, description=desc)


def test_title_seniority_implies_years():
    assert required_experience_years(_job("Senior Software Engineer")) == 4.0
    assert required_experience_years(_job("Staff Security Engineer")) == 6.0
    assert required_experience_years(_job("Principal Security Researcher")) == 8.0
    assert required_experience_years(_job("Software Engineer")) is None
    assert required_experience_years(_job("Junior Security Analyst")) == 0.0


def test_explicit_years_phrases():
    assert required_experience_years(_job("Security Engineer", "5+ years of experience")) == 5.0
    assert required_experience_years(_job("Security Engineer", "2+ years required")) == 2.0
    assert required_experience_years(_job("Security Engineer", "3-5 years experience")) == 3.0
    assert required_experience_years(_job("Security Engineer", "minimum 4 years experience")) == 4.0
    assert required_experience_years(_job("Security Engineer", "a great team")) is None


def test_broader_experience_phrases():
    # phrasings the original three patterns missed (real postings use these constantly)
    assert required_experience_years(_job("Security Engineer", "at least 5 years")) == 5.0
    assert required_experience_years(_job("Security Engineer", "minimum of 6 years")) == 6.0
    assert required_experience_years(_job("Security Engineer", "7 years required")) == 7.0
    assert required_experience_years(_job("Security Engineer", "5 years of relevant industry experience")) == 5.0
    assert required_experience_years(_job("Security Engineer", "5 yrs exp")) == 5.0
    assert required_experience_years(_job("Security Engineer", "3 to 5 years")) == 3.0
    assert required_experience_years(_job("Security Engineer", "5 years' experience")) == 5.0


def test_takes_highest_bar_across_title_and_text():
    # Senior title (~4y) + "8+ years" text -> 8; conservative so it doesn't leak through a cap.
    assert required_experience_years(_job("Senior Engineer", "8+ years in security")) == 8.0
    # Mid title with only a low explicit bar stays low.
    assert required_experience_years(_job("Software Engineer", "2+ years")) == 2.0


def test_filter_blocks_over_cap():
    f = {"max_years_experience": 2}
    assert apply_filters(_job("Senior Software Engineer"), f)  # ~4y > 2 -> blocked
    assert "experience" in apply_filters(_job("Staff Engineer"), f)
    assert apply_filters(_job("Security Engineer", "5+ years of experience"), f)


def test_filter_keeps_at_or_below_cap():
    f = {"max_years_experience": 2}
    assert apply_filters(_job("Security Engineer", "2+ years of experience"), f) is None
    assert apply_filters(_job("Junior Security Analyst"), f) is None
    assert apply_filters(_job("Security Engineer", "great team, no years stated"), f) is None


def test_filter_off_by_default():
    assert apply_filters(_job("Principal Security Engineer"), {}) is None
    assert apply_filters(_job("Staff Engineer", "10+ years"), {"max_years_experience": 0}) is None
