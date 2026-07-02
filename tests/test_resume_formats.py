"""Regression tests for real-world resume formats (categorized skills, acronyms,
'Company — Title' headings, 'Mon YYYY – Present' dates)."""
import os
import tempfile

from jobscope.resume import parse_resume

CATEGORIZED = """# Alex Roe

Punjab, India · +91 88476-80164 · alex@example.com
linkedin.com/in/alexroe

## PROFESSIONAL SUMMARY
Security researcher focused on CVE triage and detection engineering.

## TECHNICAL SKILLS
- **Vulnerability Research & Management:** Emerging-threat CVE triage, exploitability prioritization (CVSS, EPSS, KEV), Security Configuration Assessment (SCA)
- **Reverse Engineering:** IDA Pro, Ghidra, x64dbg
- **Compliance & Frameworks:** PCI DSS, ISO/IEC 27001, MITRE ATT&CK, Zero Trust
- **Languages:** C++, Python, Bash, KQL

## PROFESSIONAL EXPERIENCE

### Microsoft — Security Researcher
*MDVM · Hyderabad, India · Jun 2025 – Present*
- Triaged 30+ CVEs.

### Microsoft — Security Researcher Intern
*Hyderabad, India · May 2024 – Jul 2024*
- Reverse-engineered malware.

## EDUCATION
**Chitkara University — B.Tech CSE**
*Aug 2021 – Aug 2025*
"""


def _parse(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        path = fh.name
    try:
        return parse_resume(path)
    finally:
        os.unlink(path)


def test_location_ignores_acronyms():
    r = _parse(CATEGORIZED)
    assert r.location == "Punjab, India"  # not "CVSS, EP"


def test_categorized_skills_are_clean():
    r = _parse(CATEGORIZED)
    joined = " | ".join(r.skills)
    assert "**" not in joined
    assert "ISO/IEC 27001" in r.skills            # slash preserved
    assert "IDA Pro" in r.skills
    # category labels must not leak in as skills
    assert not any(s.lower().startswith("compliance & frameworks") for s in r.skills)
    # parenthetical noise stripped
    assert not any("(" in s for s in r.skills)


def test_company_dash_title_and_years():
    r = _parse(CATEGORIZED)
    assert any("researcher" in t.lower() for t in r.titles)
    # experience-scoped: intern (2024) + FT (2025->present) ~= 1-2y, not 4 (education excluded)
    assert 0.5 <= r.years_experience <= 3
    assert r.seniority in ("junior", "mid")


BULLET_NOISE = """# Sam Poe

Bengaluru, India \u00b7 sam@example.com

## PROFESSIONAL EXPERIENCE

### Acme \u2014 Security Researcher
*Bengaluru, India \u00b7 Jan 2025 \u2013 Present*
- Built metrics and standardized reports for engineering, analysts, and senior leadership.
- Reverse-engineered 8 malware families.

### Acme \u2014 Security Researcher Intern
*Bengaluru, India \u00b7 May 2024 \u2013 Aug 2024*
- Triaged CVEs.

## EDUCATION
**University \u2014 B.Tech**
*2021 \u2013 2025*
"""


def test_bullet_prose_does_not_leak_titles_or_seniority():
    r = _parse(BULLET_NOISE)
    # comma-separated bullet prose must not be captured as job titles
    assert all("leadership" not in t.lower() for t in r.titles), r.titles
    assert all(not t.lower().startswith("and ") for t in r.titles), r.titles
    assert any(t.lower() == "security researcher" for t in r.titles), r.titles
    # ~1yr (intern + researcher) must not read as "senior" from a stray bullet word
    assert r.seniority != "senior", r.seniority
    assert r.seniority in ("junior", "mid", "intern"), r.seniority
