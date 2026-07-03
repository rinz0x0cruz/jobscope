"""Resume parsing: Markdown / JSON Resume / PDF / plain text -> `Resume`.

Deterministic extraction (regex + a skills lexicon + section parsing). AI is not
required here; `tailor.py` can later use AI to *rewrite* bullets, but structured
extraction stays offline so `resume import` always works.
"""
from __future__ import annotations

import json
import os
import re

from .match import SENIORITY_RANK
from jobscope.core.model import Resume

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Matches "2019 - 2023", "Jun 2025 - Present", "Aug 2021 – Aug 2025", "May 2024 to Jul 2024".
YEAR_RANGE_RE = re.compile(
    r"(?:(" + _MONTH + r")\s+)?((?:19|20)\d{2})\s*(?:[-\u2013\u2014]|to)\s*"
    r"(?:(" + _MONTH + r")\s+)?((?:19|20)\d{2}|present|current|now)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"(https?://[^\s)\]]+)")

# Broad skills lexicon (extend freely in config later). Multi-word first.
SKILL_LEXICON = [
    "threat modeling", "penetration testing", "incident response", "secure code review",
    "vulnerability management", "application security", "cloud security", "network security",
    "identity and access management", "security architecture", "red team", "blue team",
    "machine learning", "data engineering", "distributed systems", "site reliability",
    "ci/cd", "infrastructure as code", "rest api", "microservices",
    "python", "golang", "go", "java", "javascript", "typescript", "c++", "c#", "rust", "ruby",
    "bash", "powershell", "sql", "nosql",
    "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "ansible", "linux",
    "react", "node.js", "django", "flask", "fastapi", "spring",
    "postgres", "mysql", "mongodb", "redis", "kafka", "elasticsearch",
    "burp suite", "metasploit", "nmap", "wireshark", "splunk", "siem", "soc",
    "owasp", "iam", "oauth", "saml", "pki", "cryptography", "zero trust",
    "sast", "dast", "sca", "devsecops", "compliance", "soc2", "iso 27001", "nist",
    "reverse engineering", "malware analysis", "kql", "kusto", "yara", "ghidra",
    "ida pro", "x64dbg", "volatility", "active directory", "assembly", "mitre att&ck",
    "pci dss", "detection engineering", "threat hunting", "osint", "git",
]


def import_resume(path: str, store, cfg: dict, name: str = "default") -> int:
    if not os.path.exists(path):
        print(f"  resume not found: {path}")
        return 1
    resume = parse_resume(path)
    # backfill contact fields from config profile if the resume omitted them
    prof = cfg.get("profile", {})
    resume.full_name = resume.full_name or prof.get("full_name", "")
    resume.email = resume.email or prof.get("email", "")
    resume.phone = resume.phone or prof.get("phone", "")
    resume.location = resume.location or prof.get("location", "")
    if prof.get("links"):
        resume.links = {**prof["links"], **resume.links}
    store.save_resume(resume, name=name)
    print(f"  imported resume [{name}]: {resume.full_name or '(name?)'} "
          f"| {len(resume.skills)} skills | seniority={resume.seniority or '?'} "
          f"| ~{resume.years_experience:g}y exp")
    if not resume.skills:
        print("  note: no skills detected -- add a '## Skills' section for best matching")
    return 0


def parse_resume(path: str) -> Resume:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return _from_json_resume(path)
    if ext == ".pdf":
        text = _pdf_text(path)
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    return _from_text(text, path)


def _pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("PDF resumes need pypdf: pip install pypdf") from exc
    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _from_json_resume(path: str) -> Resume:
    """Map the JSON Resume schema (jsonresume.org)."""
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    basics = d.get("basics", {})
    skills = [s.get("name", "") for s in d.get("skills", []) if s.get("name")]
    if not skills:
        skills = _extract_skills(json.dumps(d))
    work = d.get("work", [])
    titles = [w.get("position", "") for w in work if w.get("position")]
    links = {p.get("network", "link"): p.get("url", "") for p in basics.get("profiles", [])}
    if basics.get("url"):
        links.setdefault("website", basics["url"])
    years = _years_from_work(work)
    r = Resume(
        full_name=basics.get("name", ""),
        email=basics.get("email", ""),
        phone=basics.get("phone", ""),
        location=(basics.get("location", {}) or {}).get("city", "") or basics.get("region", ""),
        summary=basics.get("summary", ""),
        skills=skills,
        titles=titles,
        experiences=[{"title": w.get("position"), "company": w.get("name"),
                      "summary": w.get("summary", "")} for w in work],
        education=d.get("education", []),
        links={k: v for k, v in links.items() if v},
        years_experience=years,
        seniority=_infer_seniority(titles, years),
        raw_text=json.dumps(d),
        source_path=path,
    )
    return r


def _from_text(text: str, path: str) -> Resume:
    name = _guess_name(text)
    email_m = EMAIL_RE.search(text)
    phone_m = PHONE_RE.search(text)
    links = dict(_guess_links(text))
    skills = _merge_skills(_section_skills(text), _extract_skills(text))
    exp = _experience_section(text)
    titles = _guess_titles(exp)
    years = _years_from_text(exp)
    return Resume(
        full_name=name,
        email=email_m.group(0) if email_m else "",
        phone=(phone_m.group(0).strip() if phone_m else ""),
        location=_guess_location(text),
        summary=_first_paragraph(text),
        skills=skills,
        titles=titles,
        years_experience=years,
        seniority=_infer_seniority(titles, years),
        links=links,
        raw_text=text,
        source_path=path,
    )


def _guess_name(text: str) -> str:
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if not s:
            continue
        if EMAIL_RE.search(s) or URL_RE.search(s):
            continue
        words = s.split()
        if 1 < len(words) <= 5 and all(w[:1].isalpha() for w in words):
            return s
        return s[:80]
    return ""


def _guess_location(text: str) -> str:
    m = re.search(r"(?im)^\s*(?:location|based in)\s*[:\-]\s*(.+)$", text)
    if m:
        return m.group(1).strip()[:80]
    # "City, Country" or "City, ST" -- require Titlecase first token so acronyms
    # like "CVSS, EP" (from 'CVSS, EPSS, KEV') are never mistaken for a location.
    pat = re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*(?:[A-Z][a-z]{2,}|[A-Z]{2})\b)")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:6]
    for ln in lines:
        for piece in re.split(r"[\u00b7|]", ln):
            mm = pat.search(piece)
            if mm:
                return mm.group(1).strip()
    mm = pat.search(text)
    return mm.group(1).strip() if mm else ""


def _guess_links(text: str):
    for url in URL_RE.findall(text):
        low = url.lower()
        if "linkedin" in low:
            yield "linkedin", url.rstrip(".,)")
        elif "github" in low:
            yield "github", url.rstrip(".,)")
        else:
            yield "website", url.rstrip(".,)")


def _first_paragraph(text: str) -> str:
    m = re.search(r"(?is)(?:summary|profile|objective)\s*[:\n]+(.+?)(?:\n\s*\n|\n#)", text)
    if m:
        return " ".join(m.group(1).split())[:600]
    return ""


def _section_skills(text: str) -> list[str]:
    """Parse an explicit Skills section, including categorized '**Label:** a, b' lines."""
    m = re.search(
        r"(?is)(?:^|\n)[#\s]*(?:technical\s+)?skills?\s*[:\n]+(.+?)(?:\n\s*\n|\n#{1,6}\s|\Z)",
        text,
    )
    if not m:
        return []
    out, seen = [], set()
    for line in m.group(1).splitlines():
        line = re.sub(r"^[\-\*\u2022\s]+", "", line.strip())
        line = line.replace("**", "")
        line = re.sub(r"\([^)]*\)", "", line)          # drop parentheticals (WDAC, ...)
        if ":" in line:                                # drop a leading 'Category:' label
            line = line.split(":", 1)[1]
        for tok in re.split(r"[,;|]+", line):          # keep '/' so ISO/IEC 27001 survives
            t = re.sub(r"\s{2,}", " ", tok).strip("*_ ")
            if 1 < len(t) <= 45 and not t.lower().startswith(("http", "www")):
                key = t.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(t)
    return out[:60]


def _extract_skills(text: str) -> list[str]:
    low = text.lower()
    found, seen = [], set()
    for skill in SKILL_LEXICON:
        if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", low):
            if skill not in seen:
                seen.add(skill)
                found.append(skill)
    return found


def _merge_skills(primary: list[str], extra: list[str]) -> list[str]:
    out, seen = [], set()
    for s in list(primary) + list(extra):
        k = s.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _experience_section(text: str) -> str:
    """Isolate the work-experience block so education dates don't inflate tenure."""
    m = re.search(
        r"(?is)\n#{1,6}\s*(?:professional\s+|work\s+|relevant\s+)?experience\b(.*?)"
        r"(?:\n#{1,3}\s*(?:projects?|education|certification|awards|publications)\b|\Z)",
        text,
    )
    return m.group(1) if m else text


ROLE_WORDS = ("engineer", "developer", "manager", "analyst", "architect", "consultant",
              "scientist", "specialist", "lead", "director", "intern", "researcher",
              "administrator", "designer", "hunter")
_SEP_RE = re.compile(r"\s*[\u2014\u2013\-\u00b7|,]\s*")


def _looks_like_title(seg: str) -> bool:
    """True when a segment reads like a job title, not a sentence fragment."""
    if not (2 < len(seg) <= 48):
        return False
    low = seg.lower()
    if low.startswith(("http", "www", "and ", "or ", "for ", "with ", "the ", "a ", "to ", "of ")):
        return False
    if seg[-1] in ".:;":                         # sentences / trailing punctuation
        return False
    if len(seg.split()) > 6:                      # real titles are short
        return False
    if not re.search(r"\b(?:" + "|".join(ROLE_WORDS) + r")\b", low):
        return False
    first = next((ch for ch in seg if ch.isalpha()), "")
    return bool(first) and first.isupper()        # titles are Title-Cased


def _guess_titles(text: str) -> list[str]:
    """Capture role titles from headings ('### Company - Title', '**Title**') or
    compact 'Title - Company - dates' rows, ignoring bullet prose."""
    titles, seen = [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_heading = line.startswith("#") or (line.startswith("**") and line.endswith("**"))
        cleaned = line.lstrip("#").strip().strip("*").strip()
        if not (is_heading or _SEP_RE.search(cleaned)):
            continue
        for seg in _SEP_RE.split(cleaned):
            seg = seg.strip().strip("*_").strip()
            if not _looks_like_title(seg):
                continue
            low = seg.lower()
            if low in seen:
                continue
            seen.add(low)
            titles.append(seg)
    return titles[:12]


def _years_from_work(work: list[dict]) -> float:
    spans = []
    for w in work:
        start = str(w.get("startDate", ""))[:4]
        end = str(w.get("endDate", "") or "present")[:4]
        spans.append(f"{start} - {end}")
    return _years_from_text("\n".join(spans))


def _years_from_text(text: str) -> float:
    import datetime as _dt
    now = _dt.datetime.now(_dt.UTC)
    now_frac = now.year + (now.month - 1) / 12.0
    spans: list[tuple[float, float]] = []
    for m in YEAR_RANGE_RE.finditer(text):
        sm, sy, em, ey = m.groups()
        start_mon = MONTH_NUM.get((sm or "jan")[:3].lower(), 1)
        start = int(sy) + (start_mon - 1) / 12.0
        if ey.lower() in ("present", "current", "now"):
            end = now_frac
        else:
            end_mon = MONTH_NUM.get((em or "dec")[:3].lower(), 12)
            end = int(ey) + (end_mon - 1) / 12.0
        if end >= start and int(sy) >= 1970:
            spans.append((start, min(end, now_frac)))
    if not spans:
        return 0.0
    # union of merged intervals so overlapping/parallel roles don't double-count
    spans.sort()
    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return round(sum(e - s for s, e in merged), 1)


def _infer_seniority(titles: list[str], years: float) -> str:
    rank_label = {0: "intern", 1: "junior", 2: "mid", 3: "senior",
                  4: "staff", 5: "principal", 6: "director", 7: "vp", 8: "chief"}
    ranks, has_intern = [], False
    for title in titles:
        t = f" {title.lower()} "
        for word, rank in SENIORITY_RANK.items():
            if f" {word} " in t:
                if word in ("intern", "internship"):
                    has_intern = True
                else:
                    ranks.append(rank)
    if has_intern and years < 1:
        return "intern"
    # Years is the anchor; a seniority word in a title may nudge the label by at
    # most one band. So a stray "Senior" on a ~1-year resume can't claim a
    # seniority it hasn't earned, while a genuine title still lifts an
    # under-titled year count (e.g. "Senior" + 10y stays senior, not staff).
    title_rank = max(ranks) if ranks else -1
    yr_rank = _years_rank(years)
    if title_rank >= 0 and yr_rank >= 0:
        rank = min(max(title_rank, yr_rank - 1), yr_rank + 1)
        return rank_label.get(rank, "")
    if title_rank >= 0:
        return rank_label.get(title_rank, "")
    return _years_label(years)


def _years_rank(years: float) -> int:
    if years >= 10:
        return 4
    if years >= 6:
        return 3
    if years >= 3:
        return 2
    if years >= 1:
        return 1
    return -1


def _years_label(years: float) -> str:
    return {4: "staff", 3: "senior", 2: "mid", 1: "junior"}.get(
        _years_rank(years), "junior" if years else "")
