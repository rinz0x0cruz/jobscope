"""Résumé routing: pick which base résumé to tailor from when several are imported,
and report your best fit across framings.

A clearly technical / hands-on posting routes to the more technical résumé, a
clearly advisory / GRC posting to the more advisory one; ambiguous jobs fall back
to the best-fitting résumé. Depends on :mod:`.scoring` for the per-framing fit.
"""
from __future__ import annotations

from ..model import Job, Resume
from .scoring import score_job

# Discipline signals used to route a job to the best-fit resume when several are
# imported. TECHNICAL = hands-on / read-code security work; ADVISORY = consulting
# / GRC. Substring matched (case-insensitive); tune freely.
TECHNICAL_SIGNALS = [
    "reverse engineering", "reverse engineer", "malware", "exploit",
    "vulnerability research", "vuln research", "vulnerability detection",
    "vulnerability management", "disassembl", "decompil",
    "debugger", "debugging", "ida pro", "ghidra", "x64dbg", "windbg",
    "binary analysis", "shellcode", "fuzz", "detection engineering",
    "detection engineer", "security engineer", "software engineer",
    "product security", "application security", "appsec", "offensive security",
    "red team", "penetration test", "pentest", "kernel", "assembly", "firmware",
    "secure coding", "code review", "source code", "sast", "dast",
    "threat detection", "dfir", "incident response", "yara", "sigma rule",
    "cryptograph", "memory corruption", "low-level",
]
ADVISORY_SIGNALS = [
    "consultant", "consulting", "advisory", "advisor", "grc", "governance",
    "risk management", "risk assessment", "compliance", "audit", "auditor",
    "assessor", "regulatory", "stakeholder", "executive", "roadmap",
    "security posture", "posture", "third-party risk", "third party risk",
    "vendor risk", "gap assessment", "maturity assessment", "questionnaire",
    "attestation", "iso 27001", "soc 2", "pci dss", "program management",
]

DISCIPLINE_SELECT_WEIGHT = 5.0  # nudge (points) for a matching discipline on ambiguous jobs
LEAN_DECISIVE = 0.25            # |job lean| at/above this routes by discipline, score breaks ties


def _lean_counts(text: str) -> tuple[int, int]:
    t = (text or "").lower()
    tech = sum(1 for s in TECHNICAL_SIGNALS if s in t)
    adv = sum(1 for s in ADVISORY_SIGNALS if s in t)
    return tech, adv


def _lean(tech: int, adv: int) -> float:
    """Map (technical, advisory) hit counts to a lean in [-1, +1] (+1 = technical)."""
    total = tech + adv
    return (tech - adv) / total if total else 0.0


def _resume_lean(resume: Resume) -> float:
    text = resume.raw_text or " ".join(
        list(resume.skills) + list(resume.titles) + [resume.summary or ""])
    return _lean(*_lean_counts(text))


def _job_lean(job: Job) -> float:
    tt, ta = _lean_counts(job.title)
    dt, da = _lean_counts(job.description)
    return _lean(2 * tt + dt, 2 * ta + da)   # title weighted heavier than description


def select_base(job: Job, resumes: list, match_cfg: dict) -> tuple[float, str, str, str]:
    """Pick the base resume to tailor from, and report your best fit for the job.

    You are one candidate viewed through several resume "framings", so the
    headline score/tier is the *best* fit across those framings -- no framing is
    under-credited just for omitting a keyword the others happen to list. The
    returned ``base`` is which resume to tailor from: a clearly technical /
    hands-on posting routes to the more technical resume, a clearly advisory /
    GRC posting to the more advisory one (fit score only breaks lean ties);
    ambiguous jobs fall back to the best-fitting resume.
    """
    job_lean = _job_lean(job)
    cand = []  # (score, tier, rationale, name, resume_lean)
    for name, resume in resumes:
        score, tier, rationale = score_job(job, resume, match_cfg)
        cand.append((score, tier, rationale, name, _resume_lean(resume)))

    # base = which resume to tailor from
    decisive = len(resumes) > 1 and abs(job_lean) >= LEAN_DECISIVE
    if decisive:
        # clear discipline -> the most technical (or most advisory) resume,
        # regardless of a small score gap; fit score only breaks lean ties.
        direction = 1.0 if job_lean >= 0 else -1.0
        routed_name = max(cand, key=lambda c: (direction * c[4], c[0]))[3]
    else:
        # ambiguous -> best fit, discipline only a light aligned nudge
        routed_name = max(cand, key=lambda c: c[0] + DISCIPLINE_SELECT_WEIGHT * job_lean * c[4])[3]

    # headline = best fit across framings (stable ranking, nothing under-credited)
    score, tier, rationale, best_name, _ = max(cand, key=lambda c: c[0])
    if decisive:
        verb = "tailor from " if best_name != routed_name else ""
        rationale = f"{rationale} \u2192 {verb}{routed_name} ({'technical' if job_lean > 0 else 'advisory'} role)"
    return score, tier, rationale, routed_name
