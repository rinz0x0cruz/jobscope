"""Application prep + (human-in-the-loop) apply.

`prep` assembles a review-ready package: tailored resume + cover (via `tailor`),
pre-filled common answers, an index with the apply link and referral contacts,
and an optional email summary. `apply` opens the application for **you** to submit
-- with an opt-in `--assist` that pre-fills *public* ATS forms and stops before
submit. It never automates a logged-in account and never clicks submit for you.
"""
from __future__ import annotations

import os
import webbrowser

from . import ai, email, tailor
from .model import Application
from .store import now_iso

PUBLIC_ATS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
              "smartrecruiters.com", "breezy.hr", "recruitee.com", "myworkdayjobs.com")


# ---- prep ---------------------------------------------------------------
def prep(cfg: dict, store, job_id: str, notify: bool = True) -> int:
    job = store.get_job(job_id)
    if job is None:
        print(f"  job not found: {job_id}")
        return 1
    resume = store.get_resume()
    if resume is None:
        print("  no resume found. Run `resume import <path>` first.")
        return 1

    # (re)build tailored resume + cover + analysis
    rc = tailor.run(cfg, store, job_id)
    if rc != 0:
        return rc

    app = {a["job_id"]: a for a in store.applications()}.get(job_id, {})
    pkg = app.get("package_dir") or _default_pkg(cfg, job)
    enr = store.get_enrichment(job.company) if job.company else {}
    contacts = store.contacts_for(job.company) if job.company else []

    answers = _filled_answers(cfg, store, resume, job)
    _write(pkg, "filled-answers.md", answers)
    index = _index(job, app, enr, contacts)
    _write(pkg, "application.md", index)

    # optional email summary (suppressed when driven by the pipeline digest)
    if notify:
        subject = f"[jobscope] Ready to apply: {job.title} @ {job.company} ({job.tier} {job.score})"
        email.send(cfg, subject, _email_text(job, enr, contacts, pkg))

    store.set_application(Application(
        job_id=job.id, status="prepared", package_dir=pkg,
        resume_path=app.get("resume_path", ""), cover_path=app.get("cover_path", ""),
        notes=app.get("notes", ""), updated=now_iso(),
    ))
    print(f"  package ready: {pkg}")
    print(f"  review, then: python -m jobscope apply {job.id}   (add --assist for public ATS autofill)")
    return 0


# ---- apply --------------------------------------------------------------
def apply(cfg: dict, store, job_id: str, assist: bool = False) -> int:
    job = store.get_job(job_id)
    if job is None:
        print(f"  job not found: {job_id}")
        return 1
    if not job.url:
        print("  this job has no apply URL on record.")
        return 1

    assist = assist or bool(cfg.get("apply", {}).get("assist"))
    if assist and _is_public_ats(job.url):
        resume = store.get_resume()
        app = {a["job_id"]: a for a in store.applications()}.get(job_id, {})
        ok = _assisted_fill(job.url, app.get("resume_path", ""), resume)
        if not ok:
            print("  assisted fill unavailable; opening the page for manual apply.")
            webbrowser.open(job.url)
    else:
        if assist:
            print("  (not a recognized public ATS; opening for manual apply)")
        webbrowser.open(job.url)
        print(f"  opened: {job.url}")

    print("  You are in control -- review everything and click submit yourself.")
    print(f"  After submitting: python -m jobscope track --set {job.id}=applied")
    return 0


# ---- assisted fill (opt-in, public ATS, stops before submit) -----------
def _assisted_fill(url: str, resume_path: str, resume) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    field_map = _profile_fields(resume)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            filled = _autofill(page, field_map)
            _upload_resume(page, resume_path)
            print(f"  assisted fill: populated {filled} field(s). "
                  f"Review the browser, complete anything left, and SUBMIT yourself.")
            input("  Press Enter here once you've submitted (or closed) the form... ")
            browser.close()
        return True
    except Exception as e:  # noqa: BLE001 - headed browser may be unavailable
        print(f"  assisted fill error: {e}")
        return False


def _autofill(page, field_map: dict) -> int:
    filled = 0
    inputs = page.query_selector_all("input, textarea")
    for el in inputs:
        try:
            if (el.get_attribute("type") or "").lower() in ("hidden", "file", "submit", "checkbox", "radio"):
                continue
            hint = " ".join(filter(None, [
                el.get_attribute("name"), el.get_attribute("id"),
                el.get_attribute("placeholder"), el.get_attribute("aria-label"),
            ])).lower()
            for key, value in field_map.items():
                if value and key in hint:
                    if not el.input_value():
                        el.fill(value)
                        filled += 1
                    break
        except Exception:  # noqa: BLE001 - skip unfillable fields
            continue
    return filled


def _upload_resume(page, resume_path: str) -> None:
    if not resume_path or not os.path.exists(resume_path):
        return
    try:
        file_input = page.query_selector("input[type=file]")
        if file_input:
            file_input.set_input_files(resume_path)
    except Exception:  # noqa: BLE001
        pass


def _profile_fields(resume) -> dict:
    if resume is None:
        return {}
    first = (resume.full_name or "").split()[0] if resume.full_name else ""
    last = (resume.full_name or "").split()[-1] if resume.full_name and len(resume.full_name.split()) > 1 else ""
    # keys are substrings matched against field name/id/placeholder/aria-label
    return {
        "first name": first, "firstname": first, "given name": first,
        "last name": last, "lastname": last, "family name": last, "surname": last,
        "full name": resume.full_name, "name": resume.full_name,
        "email": resume.email, "phone": resume.phone, "mobile": resume.phone,
        "linkedin": resume.links.get("linkedin", ""),
        "github": resume.links.get("github", ""),
        "website": resume.links.get("website", ""),
        "portfolio": resume.links.get("website", ""),
        "city": resume.location, "location": resume.location,
    }


# ---- filled answers -----------------------------------------------------
def _filled_answers(cfg: dict, store, resume, job) -> str:
    why = ai.chat(
        cfg, store,
        system=("Write 2-3 sentences answering 'Why do you want to work here?' Specific, "
                "sincere, no clichés. Use only plausible facts."),
        user=f"Role: {job.title} at {job.company}. Candidate skills: {', '.join(resume.skills[:15])}.",
    ) or (f"I'm drawn to {job.company}'s work and the {job.title} role fits my background in "
          f"{', '.join(resume.skills[:3])}. I'm excited to contribute and grow with the team.")

    target = cfg["match"].get("min_salary") or 0
    salary = f"{target:,}+ (negotiable)" if target else "[your target range]"
    remote = "Yes" if cfg["search"].get("is_remote") else "[confirm]"
    lines = [
        f"# Pre-filled answers — {job.title} @ {job.company}",
        "",
        "Copy/paste as needed. Bracketed items need your confirmation.",
        "",
        f"- **Full name:** {resume.full_name}",
        f"- **Email:** {resume.email}",
        f"- **Phone:** {resume.phone}",
        f"- **Location:** {resume.location}",
        f"- **LinkedIn:** {resume.links.get('linkedin', '[add]')}",
        f"- **GitHub:** {resume.links.get('github', '[add]')}",
        f"- **Years of experience:** {resume.years_experience:g}",
        f"- **Open to remote:** {remote}",
        "- **Work authorization:** [confirm your status]",
        f"- **Salary expectation:** {salary}",
        "- **Notice period / availability:** [e.g., 2 weeks]",
        "- **Pronouns / EEO self-ID:** [optional -- decline to answer is fine]",
        "",
        "**Why do you want to work here?**",
        "",
        why,
    ]
    return "\n".join(lines)


# ---- package index + email ---------------------------------------------
def _index(job, app, enr, contacts) -> str:
    stock = (enr or {}).get("stock") or {}
    comp = (enr or {}).get("comp") or {}
    news = (enr or {}).get("news") or []
    lines = [
        f"# Application — {job.title} @ {job.company}",
        "",
        f"- **Fit:** {job.tier} ({job.score})  ·  {app.get('notes', '')}",
        f"- **Apply URL:** {job.url}",
        f"- **Location:** {('Remote' if job.is_remote else job.location) or job.location}",
    ]
    if comp.get("range"):
        lines.append(f"- **Comp (posting):** {comp['range']}  ·  {comp.get('levels_fyi', '')}")
    if stock.get("ticker"):
        lines.append(f"- **Stock:** {stock['ticker']} {stock.get('price', '')} "
                     f"({stock.get('change_pct', '')}%), mkt cap {stock.get('market_cap', '')}")
    elif stock.get("public") is False:
        lines.append("- **Stock:** private / pre-IPO")
    if news:
        lines.append(f"- **Recent news:** {news[0]['title']}")
    lines += ["", "## Files", "- tailored_resume.pdf / .md", "- cover_letter.pdf / .md",
              "- filled-answers.md", "- analysis.md", ""]
    if contacts:
        lines.append("## Referral leads")
        for c in contacts[:6]:
            link = c.get("profile_url") or c.get("search_url") or ""
            lines.append(f"- {c.get('name', 'lead')} ({c.get('source', '')}): {link}")
            if c.get("outreach"):
                lines.append(f"    > {c['outreach']}")
        lines.append("")
    return "\n".join(lines)


def _email_text(job, enr, contacts, pkg) -> str:
    lines = [
        f"{job.title} @ {job.company}",
        f"Fit: {job.tier} ({job.score})",
        f"Apply: {job.url}",
        f"Package: {os.path.abspath(pkg)}",
        "",
    ]
    comp = (enr or {}).get("comp") or {}
    if comp.get("range"):
        lines.append(f"Comp: {comp['range']}")
    if contacts:
        lines.append(f"Referral leads: {len(contacts)} (see application.md)")
    lines += ["", "Review the package, then submit the application yourself.",
              f"After submitting: python -m jobscope track --set {job.id}=applied"]
    return "\n".join(lines)


# ---- helpers ------------------------------------------------------------
def _is_public_ats(url: str) -> bool:
    low = url.lower()
    return any(host in low for host in PUBLIC_ATS)


def _default_pkg(cfg: dict, job) -> str:
    from .model import slugify
    return os.path.join(cfg["apply"]["package_dir"], f"{job.id}-{slugify(job.company)}")


def _write(pkg: str, name: str, content: str) -> None:
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, name), "w", encoding="utf-8") as fh:
        fh.write(content)
