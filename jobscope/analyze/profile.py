"""Search profile: an editable, résumé-derived statement of what to look for.

`resume import` seeds ``data/profile.yaml`` from your parsed résumé (target roles
from your titles + a skills→role map, your locations, remote preference). You edit
that file, and ``jobscope scan`` fetches jobs from it -- so the search follows your
résumé instead of a hand-typed keyword in config.yaml. config.search stays the
fallback when no profile exists.

Deterministic + offline: it reads the parsed :class:`Resume` and writes plain YAML.
"""
from __future__ import annotations

import os
import re

from jobscope.core.model import Resume

# Seniority words we strip so a résumé title broadens into a searchable role
# ("Security Researcher Intern" -> "Security Researcher").
_SENIORITY_WORDS = re.compile(
    r"(?i)\b(intern(ship)?|junior|jr|senior|sr|staff|principal|lead|entry[\s-]*level|"
    r"associate|head\s+of|chief|vp|director)\b")

# Skill/keyword clusters -> an adjacent role to also search for. Ordered: earlier,
# more specific roles win the cap. Purely additive to your résumé's own titles.
_ROLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("application security", "appsec", "sast", "secure code", "owasp", "product security"),
     "Application Security Engineer"),
    (("cloud security", "kubernetes", "terraform", "devsecops"), "Cloud Security Engineer"),
    (("detection", "siem", "splunk", "threat hunting", "soc", "kql"), "Detection Engineer"),
    (("penetration testing", "pentest", "burp", "metasploit", "red team", "offensive"),
     "Penetration Tester"),
    (("malware", "reverse engineering", "ghidra", "ida pro", "x64dbg"), "Malware Analyst"),
    (("incident response", "forensics", "dfir"), "Incident Response Analyst"),
    (("vulnerability", "cve", "exploit", "threat"), "Security Researcher"),
    (("data engineering", "spark", "airflow", "etl"), "Data Engineer"),
    (("machine learning", "ml", "pytorch", "tensorflow"), "Machine Learning Engineer"),
    (("security", "iam", "cryptography", "pki"), "Security Engineer"),
]

_MAX_TERMS = 6


def _profile_path(cfg: dict) -> str:
    db = (cfg.get("output", {}) or {}).get("db_path", "data/jobscope.db")
    return os.path.join(os.path.dirname(db) or ".", "profile.yaml")


def _broaden_title(title: str) -> str:
    t = _SENIORITY_WORDS.sub("", title)
    t = re.sub(r"\s{2,}", " ", t).strip(" -\u2013\u2014,|")
    return t if 2 < len(t) <= 48 else ""


def _derive_terms(resume: Resume) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        key = term.lower().strip()
        if key and key not in seen and len(terms) < _MAX_TERMS:
            seen.add(key)
            terms.append(term)

    for title in resume.titles:
        add(_broaden_title(title))
    haystack = (" ".join(resume.skills) + " " + " ".join(resume.titles)).lower()
    for keywords, role in _ROLE_HINTS:
        if any(k in haystack for k in keywords):
            add(role)
    if not terms:
        add("Software Engineer")
    return terms


def _derive_locations(resume: Resume, cfg: dict) -> list[str]:
    search = cfg.get("search", {}) or {}
    locs: list[str] = []
    if search.get("is_remote", True):
        locs.append("Remote")
    if resume.location:
        locs.append(resume.location)
    if not locs:
        locs.append(search.get("location", "Remote"))
    return list(dict.fromkeys(locs))  # dedupe, keep order


def build_profile(resume: Resume, cfg: dict, name: str) -> dict:
    """Derive the editable search profile dict from a parsed résumé."""
    return {
        "resume": name or "default",
        "seniority": resume.seniority or "",
        "years_experience": round(resume.years_experience, 1),
        "search_terms": _derive_terms(resume),
        "locations": _derive_locations(resume, cfg),
        "remote": bool((cfg.get("search", {}) or {}).get("is_remote", True)),
        "top_skills": list(resume.skills[:12]),
    }


def write_profile(path: str, prof: dict) -> str:
    import yaml
    header = (
        f'# jobscope search profile -- built from résumé "{prof.get("resume", "default")}".\n'
        "# `jobscope scan` fetches jobs from this file. Edit search_terms / locations /\n"
        "# remote below, then re-run scan. Regenerate with `jobscope profile build --force`\n"
        "# (overwrites your edits). `top_skills`/`seniority` mirror your résumé for\n"
        "# reference -- matching reads the résumé itself, not this file.\n\n")
    body = yaml.safe_dump(prof, sort_keys=False, allow_unicode=True, default_flow_style=False)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + body)
    return path


def load(cfg: dict) -> dict | None:
    """Return the stored search profile dict, or None if there isn't one."""
    path = _profile_path(cfg)
    if not os.path.exists(path):
        return None
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else None


def ensure_seeded(cfg: dict, resume: Resume, name: str) -> str | None:
    """Seed profile.yaml from a résumé on first import; never clobber existing edits."""
    path = _profile_path(cfg)
    if os.path.exists(path):
        return None
    return write_profile(path, build_profile(resume, cfg, name))


def apply_to_search(search: dict, prof: dict) -> dict:
    """Overlay a profile's fetch intent onto the base search dict (for `scan`).

    Non-empty ``search_terms`` replace the config terms; ``locations`` become one
    search profile each (reusing scan's per-profile mechanism); ``remote`` sets the
    remote flag. Empty profile fields leave the config value untouched.
    """
    s = dict(search)
    terms = [t for t in (prof.get("search_terms") or []) if str(t).strip()]
    if terms:
        s["terms"] = terms
    locations = [loc for loc in (prof.get("locations") or []) if str(loc).strip()]
    if locations:
        s["profiles"] = [{"name": loc, "location": loc} for loc in locations]
    if "remote" in prof:
        s["is_remote"] = bool(prof["remote"])
    return s


def render(prof: dict, path: str) -> str:
    years = prof.get("years_experience") or 0
    terms = prof.get("search_terms") or []
    locs = prof.get("locations") or []
    return "\n".join([
        f"  search profile ({path}):",
        f"    résumé: {prof.get('resume', '?')}   seniority: {prof.get('seniority') or '?'}"
        f"   ~{years:g}y",
        f"    search terms ({len(terms)}): {', '.join(terms) or '(none)'}",
        f"    locations: {', '.join(locs) or '(none)'}   remote: {prof.get('remote', True)}",
        "    edit this file, then `jobscope scan` fetches jobs from it.",
    ])


def run(cfg: dict, store, *, action: str = "show",
        resume_name: str | None = None, force: bool = False) -> int:
    path = _profile_path(cfg)

    if action == "build":
        resume = store.get_resume(resume_name) if resume_name else store.get_resume()
        if resume is None:
            print("  no résumé found. Run `resume import <path>` first.")
            return 1
        if os.path.exists(path) and not force:
            print(f"  profile already exists: {path}")
            print("  edit it directly, or regenerate with `jobscope profile build --force`")
            return 0
        name = resume_name or _primary_name(store)
        prof = build_profile(resume, cfg, name)
        write_profile(path, prof)
        print(f"  built search profile -> {path}")
        print(render(prof, path))
        return 0

    prof = load(cfg)
    if prof is None:
        print(f"  no search profile yet. Run `jobscope profile build` to create {path}")
        return 1
    print(render(prof, path))
    return 0


def _primary_name(store) -> str:
    try:
        names = store.list_resumes()
        return names[0][0] if names else "default"
    except Exception:  # noqa: BLE001 - store without list_resumes
        return "default"
