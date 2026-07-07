"""ATS parse check: what an applicant-tracking system extracts from your resume,
plus deterministic warnings on formatting that commonly breaks parsers, and an
optional JD keyword-coverage diff.

Deterministic-first, no AI. It reuses the same offline extraction an import runs
(:func:`jobscope.analyze.resume.parse_resume` populates ``Resume`` from the file)
and, when a job is given, :func:`jobscope.apply.tailor.analyze` for the keyword
coverage the tailor already reports -- so the "ATS view" matches what the rest of
the pipeline sees.

Sources: Medium ("How to Beat the ATS ... mistakes that get you auto-rejected")
for the formatting-risk checks; Huntr for JD keyword coverage.
"""
from __future__ import annotations

import re

from jobscope.core.model import Resume

# Glyph ranges that routinely corrupt ATS text extraction: typographic ligatures
# (fi/fl...), box-drawing (used to fake tables/columns), the Unicode private-use
# area (icon fonts), and the replacement char -- which itself means an upstream
# text extraction already failed.
_LIGATURES = re.compile(r"[\ufb00-\ufb06]")
_BOX_DRAWING = re.compile(r"[\u2500-\u257f]")
_PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")
_REPLACEMENT = "\ufffd"

# A "Skills" / "Technical Skills" heading (Markdown ### or a bare label line).
_SKILLS_HEADING = re.compile(r"(?im)^\s*#{0,6}\s*(?:technical\s+|core\s+|key\s+)?skills?\s*[:\n]")
# Any conventional experience heading, so we can warn when none is present.
_EXPERIENCE_HEADING = re.compile(
    r"^\s*#{0,6}\s*(?:professional\s+|work\s+|relevant\s+)?experience\b|"
    r"^\s*#{0,6}\s*employment\b",
    re.IGNORECASE | re.MULTILINE)

# A row that reads like two columns: text, a gap of 3+ spaces, then more text.
_COLUMN_ROW = re.compile(r"[A-Za-z0-9][^\n]*?[A-Za-z0-9]\s{3,}[A-Za-z0-9][^\n]*?[A-Za-z0-9]")

# Per-severity point deductions from a starting 100 (transparent, deterministic).
_WEIGHT = {"error": 22, "warn": 9, "info": 3}


def ats_report(resume: Resume) -> dict:
    """Deterministic "what an ATS extracts" view of a parsed resume.

    Returns the extracted fields, the parsed skills/titles, an ordered list of
    ``warnings`` ({level, code, message, hint}), and a 0-100 ``score`` for how
    ATS-friendly the resume looks.
    """
    text = resume.raw_text or ""
    warnings: list[dict] = []

    def warn(level: str, code: str, message: str, hint: str) -> None:
        warnings.append({"level": level, "code": code, "message": message, "hint": hint})

    # --- fields an ATS routes on -------------------------------------------
    if not resume.full_name:
        warn("error", "no_name", "no name parsed",
             "put your name as plain text on the first line (not inside a header/image)")
    if not resume.email:
        warn("error", "no_email", "no email parsed -- an ATS can't route your application",
             "add a plain-text email line; keep it out of the page header/footer")
    if not resume.phone:
        warn("warn", "no_phone", "no phone number parsed",
             "add a plain-text phone line (not inside a header/image)")
    if not resume.location:
        warn("info", "no_location", "no location parsed",
             "add 'City, Country' so location-filtered searches match you")

    # --- skills (the ATS keyword surface) ----------------------------------
    n_skills = len(resume.skills)
    if n_skills == 0:
        warn("error", "no_skills", "no skills parsed",
             "add a plain '## Skills' section listing tools as comma-separated text")
    elif n_skills < 5:
        warn("warn", "few_skills", f"only {n_skills} skill(s) parsed",
             "list your core tools/technologies explicitly; ATS keyword-matches them")
    if n_skills and not _SKILLS_HEADING.search(text):
        warn("info", "no_skills_section", "skills found only in prose, no dedicated Skills section",
             "add a '## Skills' heading so keyword extraction is reliable")

    # --- experience / dates / titles ---------------------------------------
    if resume.years_experience == 0:
        warn("warn", "no_dates", "no parseable employment dates",
             "use 'Mon YYYY - Mon YYYY' (or 'Present') on each role so tenure is read")
    if not resume.titles:
        warn("warn", "no_titles", "no job titles parsed",
             "put each role's title on its own line, e.g. 'Security Engineer - Acme (2021-2024)'")
    if text and not _EXPERIENCE_HEADING.search(text):
        warn("info", "no_experience_heading", "no 'Experience' heading found",
             "use a standard 'Experience' / 'Work Experience' heading ATS parsers expect")

    # --- formatting risks (from the extracted text) ------------------------
    if text:
        _formatting_warnings(resume, text, warn)

    score = 100 - sum(_WEIGHT.get(w["level"], 0) for w in warnings)
    return {
        "name": resume.full_name,
        "email": resume.email,
        "phone": resume.phone,
        "location": resume.location,
        "seniority": resume.seniority,
        "years": resume.years_experience,
        "skills": list(resume.skills),
        "titles": list(resume.titles),
        "warnings": warnings,
        "score": max(0, min(100, score)),
    }


def _formatting_warnings(resume: Resume, text: str, warn) -> None:
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]

    # Image-only / scanned PDF: almost no selectable text came out.
    if resume.source_path.lower().endswith(".pdf"):
        if len(re.sub(r"\s+", "", text)) < 200:
            warn("error", "image_pdf", "little/no text extracted -- resume looks image-based",
                 "export a text-based PDF (selectable text), not a scan or screenshot")

    # Tables: Markdown/text pipe tables or tab-delimited columns scramble in ATS.
    table_rows = sum(1 for ln in lines if ln.count("|") >= 2 or "\t" in ln)
    if table_rows >= 3:
        warn("warn", "tables", f"table/tab layout detected ({table_rows} rows)",
             "ATS parsers often scramble tables; use single-column linear text")

    # Multi-column: many rows with a wide internal gap between two text blocks.
    col_rows = sum(1 for ln in non_empty if _COLUMN_ROW.search(ln))
    if non_empty and col_rows >= 6 and col_rows / len(non_empty) >= 0.2:
        warn("warn", "multi_column", "possible multi-column layout",
             "switch to a single-column layout; columns often interleave when parsed")

    # Corrupting glyphs.
    if _REPLACEMENT in text:
        warn("error", "replacement_chars",
             "replacement characters present -- text extraction is already failing",
             "re-export as plain UTF-8; avoid decorative/embedded fonts")
    elif _LIGATURES.search(text) or _BOX_DRAWING.search(text) or _PRIVATE_USE.search(text):
        warn("warn", "risky_glyphs", "unusual glyphs detected (ligatures/box-drawing/icon fonts)",
             "re-export as plain UTF-8; decorative fonts can corrupt extracted text")


def coverage(resume: Resume, job) -> dict:
    """JD keyword-coverage diff against the parsed resume.

    Thin wrapper over :func:`jobscope.apply.tailor.analyze` so the number here is
    the same "ATS coverage %" the tailor reports. Imported lazily to keep this
    module free of the tailor's PDF/AI import chain until a job is supplied.
    """
    from jobscope.apply import tailor
    return tailor.analyze(resume, job)


# --- rendering -------------------------------------------------------------
def _fmt_list(items: list[str], limit: int = 12) -> str:
    if not items:
        return "(none)"
    shown = ", ".join(items[:limit])
    extra = len(items) - limit
    return f"{shown}, +{extra} more" if extra > 0 else shown


def render_report(report: dict, *, label: str = "", job=None, cov: dict | None = None) -> str:
    name = report["name"] or "(name not parsed)"
    head = f"  ATS parse check: {name}" + (f"  [{label}]" if label else "")
    out = [head, "  what an ATS extracts:"]
    years = report["years"]
    sen = report["seniority"] or "?"
    fields = [
        ("name", report["name"] or "(not parsed)"),
        ("email", report["email"] or "(not parsed)"),
        ("phone", report["phone"] or "(not parsed)"),
        ("location", report["location"] or "(not parsed)"),
        ("seniority", f"{sen}  (~{years:g}y experience)" if years else sen),
        ("skills", f"{len(report['skills'])} parsed -> {_fmt_list(report['skills'])}"),
        ("titles", f"{len(report['titles'])} parsed -> {_fmt_list(report['titles'], 6)}"),
    ]
    for k, v in fields:
        out.append(f"    {k:<10} {v}")

    out.append(f"  ATS-friendliness: {report['score']}/100")
    warnings = report["warnings"]
    if not warnings:
        out.append("  no formatting issues detected")
    else:
        out.append(f"  warnings ({len(warnings)}):")
        for w in warnings:
            out.append(f"    [{w['level']}]  {w['message']}")
            out.append(f"            fix: {w['hint']}")

    if job is not None and cov is not None:
        title = f"{job.title} @ {job.company or '?'}"
        out.append(f'  JD keyword coverage vs "{title}": {cov["coverage"]:g}%')
        out.append(f"    matched ({len(cov['matched'])}): {_fmt_list(cov['matched'], 16)}")
        miss = cov["missing"]
        tail = "  (surface these if you have them)" if miss else ""
        out.append(f"    missing ({len(miss)}): {_fmt_list(miss, 16)}{tail}")
    return "\n".join(out)


def run(cfg: dict, store, *, resume_name: str | None = None, job_id: str | None = None) -> int:
    resume = store.get_resume(resume_name) if resume_name else store.get_resume()
    if resume is None:
        print("  no resume found. Run `resume import <path>` first.")
        return 1
    job = None
    if job_id:
        job = store.get_job(job_id)
        if job is None:
            print(f"  job not found: {job_id}")
            return 1
    report = ats_report(resume)
    cov = coverage(resume, job) if job else None
    print(render_report(report, label=resume_name or "", job=job, cov=cov))
    return 0
