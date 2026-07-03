"""Deterministic rules for classifying job-application emails.

Pure functions only -- no I/O, no network, no LLM -- so they are trivially unit
tested and form the offline core of the ``inbox`` command. The optional AI layer
(:mod:`jobscope.ai`) may *refine* an ambiguous ``other`` classification, but is
never required: everything here works with zero external dependencies.

The pipeline is: is this email job-related? -> which signal does it carry? ->
what company/role is it about? -> which funnel status does the signal imply?
"""
from __future__ import annotations

import difflib
import re
from typing import Optional

# --- Applicant-tracking-system + job-board sender domains -------------------
# Mail about an application you submitted almost always comes from one of these
# platforms (the employer configures them), so the sending domain alone is a
# strong "this is job-related" signal even before we read the subject/body.
ATS_DOMAINS: dict[str, str] = {
    "greenhouse.io": "greenhouse",
    "us.greenhouse-mail.io": "greenhouse",
    "eu.greenhouse-mail.io": "greenhouse",
    "hire.lever.co": "lever",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
    "notifications.ashbyhq.com": "ashby",
    "myworkday.com": "workday",
    "myworkdayjobs.com": "workday",
    "wd1.myworkdaysite.com": "workday",
    "icims.com": "icims",
    "talent.icims.com": "icims",
    "smartrecruiters.com": "smartrecruiters",
    "smartrecruitersmail.com": "smartrecruiters",
    "successfactors.com": "successfactors",
    "sapsf.com": "successfactors",
    "taleo.net": "taleo",
    "workable.com": "workable",
    "candidates.workable.com": "workable",
    "jobvite.com": "jobvite",
    "hire.jobvite.com": "jobvite",
    "bamboohr.com": "bamboohr",
    "app.bamboohr.com": "bamboohr",
    "breezy.hr": "breezy",
    "rippling-mail.com": "rippling",
    "gem.com": "gem",
    "ashby.email": "ashby",
    "eightfold.ai": "eightfold",
    "paylocity.com": "paylocity",
}

# Broader job boards / networks that also send application confirmations.
JOB_DOMAINS: dict[str, str] = {
    "linkedin.com": "linkedin",
    "e.linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "indeedemail.com": "indeed",
    "glassdoor.com": "glassdoor",
    "ziprecruiter.com": "ziprecruiter",
    "wellfound.com": "wellfound",
    "angel.co": "wellfound",
    "dice.com": "dice",
    "monster.com": "monster",
    "hired.com": "hired",
    "otta.com": "otta",
}

# --- Signal keyword rules (checked in precedence order) ---------------------
# Rejections and offers are checked first because those emails routinely contain
# words like "interview" or "position" that would otherwise mis-fire a weaker
# rule. Each entry is (signal, [compiled patterns]).
_RULES: list[tuple[str, list[str]]] = [
    ("rejection", [
        r"unfortunately",
        r"we regret",
        r"regret to inform",
        r"not (?:be )?(?:moving|proceeding|going) forward",
        r"won'?t be (?:moving|proceeding) forward",
        r"will not be (?:moving|proceeding|progressing)",
        r"decided (?:to (?:move|proceed) (?:forward|ahead) )?with other candidates",
        r"move forward with other",
        r"pursue other candidates",
        r"other candidates whose",
        r"no longer (?:being )?(?:under )?consider",
        r"not (?:been )?(?:selected|shortlisted|successful)",
        r"not (?:to )?(?:be )?(?:selected|progress)",
        r"position has been filled",
        r"role has been filled",
        r"filled the (?:position|role|vacancy)",
        r"after (?:careful|much) (?:consideration|thought)",
        r"not (?:a|the right) (?:match|fit) (?:at this time|for this)",
        r"decided not to (?:move|proceed|continue)",
        r"wish you (?:the best|success|luck)",
    ]),
    ("offer", [
        r"pleased to (?:offer|extend)",
        r"(?:excited|thrilled|happy|delighted) to (?:offer|extend)",
        r"offer of employment",
        r"(?:job|employment|formal|written|verbal) offer",
        r"offer letter",
        r"extend(?:ing)? (?:you )?an offer",
        r"we would like to offer you",
        r"congratulations[!,. ].{0,60}offer",
    ]),
    ("assessment", [
        r"\bassessment\b",
        r"coding (?:challenge|test|exercise|assessment)",
        r"take[- ]home (?:assignment|challenge|test|exercise)",
        r"online (?:assessment|test|coding)",
        r"technical (?:screen(?:ing)?|challenge|exercise|assessment)",
        r"\bOA\b",
        r"hackerrank|codility|codesignal|hackerearth|karat|coderpad|codingame",
        r"skills? (?:test|assessment)",
        r"complete (?:the|a|your) (?:assessment|challenge|test)",
    ]),
    ("interview", [
        r"\binterview\b",
        r"schedule (?:a |an |your )?(?:call|time|chat|conversation|meeting|screen)",
        r"(?:phone|video|recruiter|hiring manager|initial) screen",
        r"(?:your|share your|let us know your) availability",
        r"(?:next|following) steps? (?:in|of|for) (?:the|your|our)",
        r"like to (?:speak|chat|meet|connect|talk|discuss)",
        r"set up (?:a |some )?(?:call|time|chat|meeting)",
        r"book (?:a )?time",
        r"calendly\.com|savvycal|cal\.com",
        r"invite you to (?:a|an|the|interview)",
        r"move(?:d)? (?:you )?(?:to|forward to|on to) the (?:next|interview)",
    ]),
    ("confirmation", [
        r"thank(?:s| you) for (?:applying|your application|your interest)",
        r"application (?:has been |was |is )?(?:received|submitted|complete)",
        r"(?:we|we've|we have) received your application",
        r"successfully (?:applied|submitted)",
        r"your application (?:to|for|has been received)",
        r"we appreciate your interest",
        r"application (?:confirmation|received)",
        r"has been received and",
        r"we('| ha)?ve got your application",
    ]),
    ("recruiter", [
        r"came across your (?:profile|resume|r\u00e9sum\u00e9|background|linkedin)",
        r"your (?:profile|background|experience) (?:stood out|caught|is a)",
        r"reaching out (?:because|regarding|about|to)",
        r"i'?m (?:a |an )?(?:recruiter|talent|technical sourcer|sourcer)",
        r"(?:exciting|great|new) (?:role|opportunity|opening)",
        r"opportunity (?:at|with|for)",
        r"(?:sourced|found) your (?:profile|resume)",
        r"would you be (?:open|interested)",
    ]),
]

_COMPILED: list[tuple[str, list[re.Pattern[str]]]] = [
    (sig, [re.compile(p, re.I) for p in pats]) for sig, pats in _RULES
]

# Signals that on their own mark an email as job-related even from an unknown
# sender domain (a recruiter cold-email from a random domain is intentionally
# NOT enough -- too noisy -- unless the domain is a known ATS/board).
_STRONG_SIGNALS = {"confirmation", "rejection", "interview", "assessment", "offer"}

# Signal -> coarse funnel status (jobscope's model.STATUSES). "" = no change.
_SIGNAL_STATUS: dict[str, str] = {
    "confirmation": "applied",
    "recruiter": "applied",
    "assessment": "interview",
    "interview": "interview",
    "offer": "offer",
    "rejection": "rejected",
    "other": "",
}

# Forward-only ranking of the funnel; a later email never drags a status
# backwards (a stray late "application received" can't undo an "offer").
_STATUS_RANK = {"new": 0, "prepared": 1, "applied": 2, "interview": 3, "offer": 4}

_COMPANY_SUFFIXES = re.compile(
    r"\b(?:inc|inc\.|llc|ltd|ltd\.|limited|corp|corp\.|corporation|co|co\.|"
    r"gmbh|plc|sa|ag|bv|pvt|private|technologies|technology|labs|software|"
    r"solutions|systems|group|holdings|team|talent|recruiting|recruitment|"
    r"careers|hr|people|hiring)\b", re.I)

# "no-reply", "careers", etc. -- sender local-parts that are not a company name.
_NOREPLY_LOCALPARTS = {
    "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply", "careers",
    "jobs", "recruiting", "recruitment", "talent", "hr", "hello", "notifications",
    "notification", "mailer", "mail", "team", "people", "hiring", "apply",
}


def domain_platform(from_domain: str) -> str:
    """Return the ATS/board platform for a sender domain (suffix match), or ""."""
    d = (from_domain or "").lower().strip()
    for table in (ATS_DOMAINS, JOB_DOMAINS):
        if d in table:
            return table[d]
        for known, platform in table.items():
            if d.endswith("." + known) or d == known:
                return platform
    return ""


def is_ats_domain(from_domain: str) -> bool:
    """True only for applicant-tracking-system domains (Greenhouse/Lever/Ashby/
    Workday/...), which send application mail exclusively -- unlike job boards
    (LinkedIn/Indeed/Glassdoor) that also blast alerts and newsletters."""
    d = (from_domain or "").lower().strip()
    if d in ATS_DOMAINS:
        return True
    return any(d == k or d.endswith("." + k) for k in ATS_DOMAINS)


def classify_signal(from_addr: str, subject: str, body: str) -> str:
    """Classify an email into one of model.SIGNALS using ordered keyword rules.

    Precedence (rejection/offer first) avoids the common false-positive where a
    rejection or offer email also mentions "interview" or "application".
    """
    text = f"{subject or ''}\n{body or ''}"
    for signal, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(text):
                return signal
    return "other"


def is_job_related(from_domain: str, signal: str) -> bool:
    """Keep an email only if it comes from an ATS domain (which sends only
    application mail), or it carries a strong application-lifecycle signal.
    Job-board and unknown domains without a strong signal are dropped so
    newsletters/alerts/social noise never reach the funnel."""
    if is_ats_domain(from_domain):
        return True
    return signal in _STRONG_SIGNALS


# Job-board digests / alerts / community mail that isn't real application status
# (e.g. "Glassdoor Community", "LinkedIn Job Alerts"). These share a job-board
# domain with genuine confirmations, so filter them by sender name/address.
_NOISE_SENDER = re.compile(
    r"\b(?:community|job\s*alerts?|jobalerts?|digest|newsletter|"
    r"weekly\s+(?:digest|update|roundup)|bulletin|spotlight)\b", re.I)


def is_noise_sender(from_name: str, from_addr: str) -> bool:
    return bool(_NOISE_SENDER.search(f"{from_name or ''} {from_addr or ''}"))


def signal_to_status(signal: str) -> str:
    """Map a granular email signal to a coarse funnel status ("" = no change)."""
    return _SIGNAL_STATUS.get(signal, "")


def advance_status(old: str, new: str) -> str:
    """Merge a newly-observed status with the stored one, never moving backwards.

    ``rejected`` is terminal (a rejection can arrive from any prior stage and
    then sticks); otherwise the higher-ranked of the two wins.
    """
    if not old:
        return new
    if old == "rejected":
        return "rejected"
    if new == "rejected":
        return "rejected"
    if _STATUS_RANK.get(new, 0) >= _STATUS_RANK.get(old, 0):
        return new
    return old


def normalize_company(name: str) -> str:
    """Lowercased company key with legal/recruiting suffixes and noise removed."""
    n = (name or "").lower()
    n = re.sub(r"[|/@].*$", "", n)                 # drop "Acme | Careers", "Acme@..."
    n = _COMPANY_SUFFIXES.sub(" ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: and whitespace for a stable thread key."""
    s = re.sub(r"^\s*(?:re|fwd|fw)\s*:\s*", "", subject or "", flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def best_company_match(company: str, candidates: list[str], cutoff: float = 0.86) -> Optional[str]:
    """Fuzzy-match a parsed company against normalized candidate keys (stdlib
    difflib, no extra deps). Returns the matching candidate key, or None."""
    key = normalize_company(company)
    if not key or not candidates:
        return None
    if key in candidates:
        return key
    hits = difflib.get_close_matches(key, candidates, n=1, cutoff=cutoff)
    return hits[0] if hits else None


# Subject patterns that carry "<role> at <company>" / "your application to <company>".
_ROLE_AT_COMPANY = re.compile(
    r"(?:application|apply(?:ing)?|candidacy|interest)\s+(?:for|to|as|in)\s+"
    r"(?:the\s+|our\s+)?(?P<role>[A-Za-z0-9 ,+/&().-]{2,60}?)\s+"
    r"(?:role|position|opening|job|vacancy)?\s*(?:at|with|@)\s+(?P<company>[A-Za-z0-9 &.,'-]{2,50})",
    re.I)
_APPLICATION_TO = re.compile(
    r"(?:your\s+)?(?:application\s+(?:to|at|with)|appl(?:y|ied|ying)\s+(?:to|with))\s+"
    r"(?P<company>[A-Za-z0-9 &.,'-]{2,50}?)"
    r"(?=\s+(?:has|have|is|was|been|received|confirmation|confirmed|team|update|status|"
    r"application|role|roles|position|for|at|in|with|as|and|please|thank|job)\b|[!.?,]|$)", re.I)
# "<Company> job application" (e.g. "received your Target job application").
_JOB_APPLICATION = re.compile(
    r"(?:your|the)\s+(?P<company>[A-Za-z0-9 &.'-]{2,40}?)\s+job\s+application\b", re.I)
_ROLE_DASH = re.compile(
    r"^(?P<company>[A-Za-z0-9 &.,'-]{2,50}?)\s*[-\u2013\u2014|:]\s*(?P<role>[A-Za-z0-9 ,+/&().-]{2,60})$")


def parse_company_role(from_name: str, from_domain: str, subject: str,
                       body: str = "") -> tuple[str, str]:
    """Best-effort extraction of (company, role) from an email.

    Company is taken from the sender display name where that is meaningful,
    otherwise from subject patterns; role is parsed from the subject. Both may
    be "" -- callers must tolerate missing values.
    """
    subject = subject or ""
    role = ""
    company = ""

    m = _ROLE_AT_COMPANY.search(subject)
    if m:
        role = _clean(m.group("role"))
        company = _clean(_strip_company_noise(m.group("company")))

    if not company:
        m = _APPLICATION_TO.search(subject)
        if m:
            company = _clean(_strip_company_noise(m.group("company")))

    if not company:
        m = _JOB_APPLICATION.search(subject)
        if m:
            company = _clean(_strip_company_noise(m.group("company")))

    if not company:                      # body as a last resort (subject wins)
        m = _APPLICATION_TO.search(body or "")
        if m:
            company = _clean(_strip_company_noise(m.group("company")))

    # Sender display name is often the real company ("Databricks Recruiting").
    if not company:
        company = _company_from_sender(from_name, from_domain)

    if not role:
        m = _ROLE_DASH.match(subject.strip())
        if m:
            role = _clean(m.group("role"))
            company = company or _clean(m.group("company"))

    return company, role


def _company_from_sender(from_name: str, from_domain: str) -> str:
    name = _clean(re.split(r"[|@<]", from_name or "")[0])
    # Drop pure-noise display names ("Recruiting", "No Reply", "Careers Team").
    stripped = normalize_company(name)
    if stripped and stripped not in _NOREPLY_LOCALPARTS and len(stripped) > 1:
        return _title(name)
    # Fall back to the registrable part of a non-ATS corporate domain.
    plat = domain_platform(from_domain)
    if not plat:
        d = (from_domain or "").lower()
        parts = [p for p in d.split(".") if p not in ("com", "io", "co", "net",
                 "org", "ai", "app", "mail", "email", "hr", "www", "jobs", "careers")]
        if parts:
            return _title(parts[-1])
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip(" \t\r\n-\u2013\u2014|:,.")
    # Strip a trailing recruiting/careers tag left on a company token.
    s = _COMPANY_SUFFIXES.sub("", s).strip(" -|:,.")
    return re.sub(r"\s+", " ", s).strip()


# Trailing status/verb phrases that get glued onto a company captured from a
# subject line ("Application to Acme received" -> company "Acme").
_COMPANY_TRAILING = re.compile(
    r"\s+(?:has been|have been|is|was|been|received|confirmation|confirmed|update|status|"
    r"team|application|applications|please|thank).*$", re.I)


def _strip_company_noise(s: str) -> str:
    return _COMPANY_TRAILING.sub("", s or "").strip()


def _title(s: str) -> str:
    s = _clean(s)
    return s if any(c.isupper() for c in s) else s.title()
