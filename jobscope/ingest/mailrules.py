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

# --- Newsletter / content-publishing platforms ------------------------------
# These blast blog posts, digests, course/challenge announcements, and consumer
# transactional receipts (food delivery, etc.) -- never real application status --
# yet their subjects routinely collide with lifecycle keywords (a "Coding
# Challenge" newsletter reads as an "assessment", a course "Training & Assessment"
# enrollment as an "assessment", a food "order confirmation" as a lifecycle event).
# Mail from these domains is dropped up front, even when it scores an otherwise-
# strong signal, so it never reaches the funnel. Distinct from _RELAY_DOMAINS (ESPs
# that relay *employer* mail): here the domain itself is the publisher, so it is
# never job-related.
NEWSLETTER_DOMAINS: frozenset[str] = frozenset({
    "substack.com",
    "medium.com",
    "beehiiv.com",
    "buttondown.email",
    "buttondown.com",
    "ghost.io",
    "tinyletter.com",
    "getrevue.co",
    "mailerlite.com",
    "convertkit-mail.com",
    "convertkit-mail2.com",
    "thinkific.com",   # online-course platform: "Training & Assessment" enrollments read as an assessment
    "eatclub.in",      # food delivery: "order confirmation" receipts read as lifecycle events
})

# --- Weighted signal keywords -----------------------------------------------
# Each signal accumulates a weighted score from the phrases it matches (see
# score_signals + classify_scored). Weights encode how strongly a phrase implies
# the signal: 3 = decisive, 2 = moderate, 1 = weak / boilerplate-prone (e.g.
# "next steps" and "invite you to a conversation" also appear in confirmations).
# A phrase found in the SUBJECT counts double one found only in the body.
_WEIGHTED_RULES: list[tuple[str, list[tuple[str, int]]]] = [
    ("rejection", [
        (r"unfortunately", 2),
        (r"we regret|regret to inform", 3),
        (r"not (?:be )?(?:moving|proceeding|going) forward", 3),
        (r"won'?t be (?:moving|proceeding) forward", 3),
        (r"will not be (?:moving|proceeding|progressing)", 3),
        (r"decided (?:to (?:move|proceed) (?:forward|ahead) )?with other candidates", 3),
        (r"move forward with other|pursue other candidates|other (?:candidates whose|applicants)", 3),
        (r"no longer (?:being )?(?:under )?consider", 3),
        (r"not (?:been )?(?:selected|shortlisted|successful)", 3),
        (r"not (?:to )?(?:be )?(?:selected|progress)", 2),
        (r"(?:position|role) has been filled|filled the (?:position|role|vacancy)", 3),
        (r"after (?:careful|much) (?:consideration|thought)", 2),
        (r"not (?:a|the right) (?:match|fit) (?:at this time|for this)", 3),
        (r"decided not to (?:move|proceed|continue)", 3),
        (r"wish you (?:the best|success|luck|well)|future (?:endeavou?rs|opportunities)", 2),
        (r"too many (?:qualified )?(?:candidates|applicants)|more closely (?:aligned|matched)", 2),
    ]),
    ("offer", [
        (r"pleased to (?:offer|extend)", 3),
        (r"(?:excited|thrilled|happy|delighted) to (?:offer|extend)", 3),
        (r"offer of employment", 3),
        (r"(?:job|employment|formal|written|verbal) offer", 3),
        (r"offer letter", 3),
        (r"extend(?:ing)? (?:you )?an offer", 3),
        (r"we would like to offer you", 3),
        (r"congratulations[!,. ].{0,60}offer", 3),
        (r"welcome (?:aboard|to the team)", 2),
    ]),
    ("assessment", [
        (r"\bassessment\b", 3),
        (r"coding (?:challenge|test|exercise|assessment)", 3),
        (r"take[- ]home (?:assignment|challenge|test|exercise)", 3),
        (r"online (?:assessment|test|coding)", 3),
        (r"technical (?:screen(?:ing)?|challenge|exercise|assessment)", 2),
        (r"\bOA\b", 2),
        (r"hackerrank|codility|codesignal|hackerearth|karat|coderpad|codingame", 3),
        (r"skills? (?:test|assessment)", 2),
        (r"complete (?:the|a|your) (?:assessment|challenge|test)", 3),
    ]),
    ("interview", [
        (r"\binterview\b", 3),
        (r"schedule (?:a |an |your )?(?:call|time|chat|conversation|meeting|screen)", 3),
        (r"(?:phone|video|recruiter|hiring manager|initial) screen", 3),
        (r"(?:your|share your|let us know your) availability", 2),
        (r"next steps?.{0,40}(?:schedul|interview|call|conversation|availab|meet|chat)", 1),
        (r"like to (?:speak|chat|meet|connect|talk|discuss)", 2),
        (r"set up (?:a |some )?(?:call|time|chat|meeting)", 2),
        (r"book (?:a )?time", 2),
        (r"calendly\.com|savvycal|cal\.com", 3),
        (r"invit(?:e|ing) you (?:to|for) (?:an? )?(?:interview|call|conversation|chat|screen(?:ing)?|meeting)", 2),
        (r"move(?:d)? (?:you )?(?:to|forward to|on to) the (?:next|interview)", 2),
        (r"\b(?:on\s+)?(?:mon|tues|wednes|thurs|fri)day\b.{0,30}\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", 2),
        (r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", 1),
    ]),
    ("confirmation", [
        (r"thank(?:s| you) for (?:applying|your application|your interest)", 2),
        (r"application (?:has been |was |is )?(?:received|submitted|complete)", 2),
        (r"(?:we|we've|we have) received your application", 2),
        (r"successfully (?:applied|submitted)", 2),
        (r"your application (?:to|for|has been received)", 2),
        (r"we appreciate your interest", 1),
        (r"application (?:confirmation|received)", 2),
        (r"has been received and", 1),
        (r"we('| ha)?ve got your application", 2),
    ]),
    ("recruiter", [
        (r"came across your (?:profile|resume|r\u00e9sum\u00e9|background|linkedin)", 2),
        (r"your (?:profile|background|experience) (?:stood out|caught|is a)", 2),
        (r"reaching out (?:because|regarding|about|to)", 1),
        (r"i'?m (?:a |an )?(?:recruiter|talent|technical sourcer|sourcer)", 2),
        (r"(?:exciting|great|new) (?:role|opportunity|opening)", 1),
        (r"opportunity (?:at|with|for)", 1),
        (r"(?:sourced|found) your (?:profile|resume)", 2),
        (r"would you be (?:open|interested)", 1),
    ]),
]

_WEIGHTED_COMPILED: list[tuple[str, list[tuple[re.Pattern[str], int]]]] = [
    (sig, [(re.compile(p, re.I), w) for p, w in pats]) for sig, pats in _WEIGHTED_RULES
]

# Scoring knobs for the weighted classifier (see score_signals/classify_scored).
_PRECEDENCE = ["rejection", "offer", "assessment", "interview", "confirmation", "recruiter"]
_SUBJECT_MULT = 2       # a keyword in the subject counts double a body keyword
_BODY_MULT = 1
_DECISIVE = 3           # a terminal rejection/offer score at/above this wins outright
_SUBJECT_CONFIRM = 4    # a confirmation keyword in the subject (2 x _SUBJECT_MULT)
_SCORE_FLOOR = 2        # minimum score to count as a real verdict (else "other")
_TIE_MARGIN = 2         # top must beat the runner-up by this margin to be confident

# Conditional clauses ("if you are not selected...", "if you don't hear from us...",
# "should you not be selected...") describe a HYPOTHETICAL future, not a decision.
# Application-received acknowledgments routinely carry them ("if you are not
# selected, keep an eye on our jobs page"; "if you don't hear from us in four
# weeks, you were likely not a fit"), so the rejection signal is re-scored with
# these clauses removed -- a real rejection states its decision unconditionally.
_CONDITIONAL_CLAUSE = re.compile(
    r"(?is)\b(?:if|should you|unless|in the event|in case|whether or not)\b[^.!?\n]*")


def _strip_conditional(text: str) -> str:
    """Drop conditional clauses so a *hypothetical* rejection in an acknowledgment
    ("if you are not selected...") isn't scored as a real rejection."""
    return _CONDITIONAL_CLAUSE.sub(" ", text or "")


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
    "hrms", "hcm", "workday", "taleo", "system", "portal", "admin", "info",
}

# Tokens that are never a real company -- they leak from body filler like
# "...at this time" / "applying to us" or status words, and must be discarded.
_COMPANY_STOP = {
    "us", "you", "your", "this time", "the moment", "present", "now", "today",
    "here", "the team", "our team", "the company", "the position", "the role",
    "a", "an", "the", "application", "applications", "update", "status",
    "confirmation", "received", "team", "job", "role", "position", "opening",
}

# Email-service / HR-platform domains that RELAY employer mail but are not the
# employer, so their registrable name must never be used as the company.
_RELAY_DOMAINS = {
    "amazonses.com", "sparkpostmail.com", "sparkpost.com", "sendgrid.net",
    "sendgrid.com", "mailgun.org", "mandrillapp.com", "mcsv.net", "rsgsv.net",
    "oracle.com", "outlook.com", "office365.com", "sapsf.com",
    "successfactors.com", "darwinbox.in", "darwinbox.com", "ycombinator.com",
}

# Subdomain / TLD labels stripped when deriving a company from a domain.
_DOMAIN_NOISE = {
    "com", "io", "co", "net", "org", "ai", "app", "inc", "mail", "email",
    "hr", "www", "jobs", "careers", "recruiting", "talent", "notifications",
    "e", "us", "eu", "in", "uk", "gov", "edu",
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


def company_from_domain(from_domain: str) -> str:
    """Company name from a *direct* employer sending domain (zscaler.com ->
    "Zscaler", tide.co -> "Tide"). Returns "" for ATS/job-board/relay domains,
    whose registrable name is a platform/ESP, not the employer."""
    d = (from_domain or "").lower().strip().strip(".")
    if not d or domain_platform(d):
        return ""
    if any(d == r or d.endswith("." + r) for r in _RELAY_DOMAINS):
        return ""
    labels = [p for p in d.split(".") if p not in _DOMAIN_NOISE]
    if not labels:
        return ""
    name = labels[-1]
    if len(name) < 2 or name.isdigit():
        return ""
    return _title(name)


def score_signals(subject: str, body: str) -> dict[str, int]:
    """Weighted keyword score per signal. A keyword found in the SUBJECT counts
    double one found only in the body (the subject is the stronger cue)."""
    subject = subject or ""
    body = body or ""
    scores = {sig: 0 for sig in _PRECEDENCE}
    for sig, pats in _WEIGHTED_COMPILED:
        total = 0
        for pat, weight in pats:
            if pat.search(subject):
                total += weight * _SUBJECT_MULT
            elif body and pat.search(body):
                total += weight * _BODY_MULT
        scores[sig] = total
    return scores


def classify_scored(subject: str, body: str) -> tuple[str, dict[str, int], bool, list[str]]:
    """Deterministic weighted-keyword classification with an ambiguity flag.

    Returns ``(signal, scores, ambiguous, tied)``. ``ambiguous`` is True only when
    two or more signals score within ``_TIE_MARGIN`` of the top (all above the
    floor) -- the caller may then defer to the optional quorum layer. The verdict
    is otherwise fully deterministic:

    * a decisive terminal signal (rejection/offer) wins from anywhere -- a
      rejection counts only if it survives de-conditionalization, so an
      acknowledgment's "if you are not selected..." boilerplate is not a rejection;
    * else a clear application-received SUBJECT is a confirmation even when the
      body is padded with interview/recruiter boilerplate ("next steps", "invite
      you to a conversation") -- ATS confirmations routinely carry that text;
    * else the highest weighted score wins, exact ties broken by _PRECEDENCE.
    """
    subject = subject or ""
    body = body or ""
    scores = score_signals(subject, body)
    subj = score_signals(subject, "")
    # Discount CONDITIONAL rejections: re-score the rejection signal with
    # hypothetical clauses removed, so an acknowledgment's "if you are not
    # selected, keep an eye on our page" / "if you don't hear from us ... not a
    # fit" boilerplate never reads as a real (unconditional) rejection.
    scores["rejection"] = score_signals(subject, _strip_conditional(body))["rejection"]
    # 1. Terminal signals are decisive from anywhere (rarely boilerplate); the
    #    rejection must survive de-conditionalization to count here.
    for sig in ("rejection", "offer"):
        if scores[sig] >= _DECISIVE:
            return sig, scores, False, [sig]
    # 2. Subject authority: an application-received SUBJECT is a confirmation even
    #    when the body is padded with interview/recruiter boilerplate ("next
    #    steps", "invite you to a conversation") -- ATS confirmations carry that.
    if subj["confirmation"] >= _SUBJECT_CONFIRM and not subj["interview"] and not subj["assessment"]:
        return "confirmation", scores, False, ["confirmation"]
    # 3. Highest weighted score wins; >=2 within the margin is an ambiguous tie.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], _PRECEDENCE.index(kv[0])))
    top, top_score = ranked[0]
    if top_score < _SCORE_FLOOR:
        return "other", scores, False, []
    tied = [s for s, sc in ranked if sc >= _SCORE_FLOOR and (top_score - sc) < _TIE_MARGIN]
    ambiguous = len(tied) >= 2
    return top, scores, ambiguous, tied


def classify_signal(from_addr: str, subject: str, body: str) -> str:
    """Deterministic signal for an email -- the weighted-keyword verdict, ignoring
    the ambiguity flag. ``from_addr`` is accepted for call-site compatibility."""
    return classify_scored(subject, body)[0]


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


def is_newsletter_domain(from_domain: str) -> bool:
    """True for content/newsletter platforms (Substack, Medium, Beehiiv, ...),
    whose blog/digest/challenge blasts are never application status but whose
    subjects often collide with lifecycle keywords. Such mail is dropped before
    it can reach the funnel, even when it scores a strong signal."""
    d = (from_domain or "").lower().strip().strip(".")
    if not d:
        return False
    return any(d == k or d.endswith("." + k) for k in NEWSLETTER_DOMAINS)


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
# "thank you for your interest in <Company>" (rejection/confirmation phrasing).
_INTEREST_IN = re.compile(
    r"interest(?:ed)?\s+in\s+(?:working\s+(?:at|with)\s+|joining\s+)?"
    r"(?P<company>[A-Za-z0-9][A-Za-z0-9 &.'-]{1,49}?)"
    r"(?=[!.?,]|\s+(?:team|careers?|for|and|as|to|has|is|was|been|please|thank|we)\b|$)",
    re.I)
# "... at <Company>" where Company is a Proper Noun: the capitalised start
# filters filler like "at this time"; stop at pipe/paren/punctuation or line end.
_AT_COMPANY = re.compile(
    r"\bat\s+(?P<company>[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z0-9][A-Za-z0-9&.'-]*){0,3})"
    r"(?=\s*[|(]|[!.?,)]|\s+(?:for|and|as|team|careers?)\b|$)")


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
        company = _pick(_strip_company_noise(m.group("company")))

    for pattern in (_APPLICATION_TO, _INTEREST_IN, _JOB_APPLICATION, _AT_COMPANY):
        if company:
            break
        m = pattern.search(subject)
        if m:
            company = _pick(_strip_company_noise(m.group("company")))

    if not company:                      # body as a last resort (subject wins)
        m = _APPLICATION_TO.search(body or "")
        if m:
            company = _pick(_strip_company_noise(m.group("company")))

    # Sender display name is usually the real company ("Databricks Recruiting" ->
    # Databricks). Its own fallback derives a direct employer domain when the
    # display is noise/empty (zscaler.com -> Zscaler), so a real display name is
    # preferred over a bare domain acronym (mlp.com).
    if not company:
        company = _pick(_company_from_sender(from_name, from_domain))

    if not role:
        m = _ROLE_DASH.match(subject.strip())
        if m:
            role = _clean(m.group("role"))
            if not company:
                cand = _strip_company_noise(m.group("company"))
                if len(cand.split()) <= 3:
                    company = _pick(cand)

    return company, role


def _company_from_sender(from_name: str, from_domain: str) -> str:
    name = _clean(re.split(r"[|@<]", from_name or "")[0])
    # Drop pure-noise display names ("Recruiting", "No Reply", "Careers Team").
    stripped = normalize_company(name)
    if stripped and stripped not in _NOREPLY_LOCALPARTS and len(stripped) > 1:
        return _title(name)
    # Fall back to a direct employer domain (skips ATS/board/relay platforms).
    return company_from_domain(from_domain)


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip(" \t\r\n-\u2013\u2014|:,.")
    # Strip a trailing recruiting/careers tag left on a company token.
    s = _COMPANY_SUFFIXES.sub("", s).strip(" -|:,.")
    return re.sub(r"\s+", " ", s).strip()


def _valid_company(c: str) -> bool:
    """Reject empty/too-short tokens and known body filler ("us", "this time")."""
    key = normalize_company(c)
    return (bool(key) and len(key) > 1
            and key not in _COMPANY_STOP and key not in _NOREPLY_LOCALPARTS)


def _pick(s: str) -> str:
    """Clean a candidate company, returning it only if it is a plausible name."""
    c = _clean(s)
    return c if _valid_company(c) else ""


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
