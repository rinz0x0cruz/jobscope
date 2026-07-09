"""Regression corpus of real inbox false positives + how the parser resolves them.

Every row below is a real message that once mis-classified on the dashboard. Read
together they are the *taxonomy of failure modes* the deterministic parser guards
against -- the "parse instruction" distilled from production mistakes. When a fresh
false positive turns up, add a row here so the fix is pinned by a concrete example
instead of living only inside a domain list or a regex.

Failure modes
-------------
1. NON-JOB SENDER, keyword collision
   A consumer/transactional or content-platform sender whose subject happens to
   collide with a lifecycle keyword: a food-delivery receipt ("order
   confirmation"), an online-course enrollment ("Training & Assessment"), a
   newsletter ("Coding Challenge"). It is never a real application, yet it can
   score a *strong* signal from a non-ATS domain.
   -> RESOLUTION: drop by sender domain up front (`is_newsletter_domain`),
      regardless of signal. It never reaches the funnel.

2. PLATFORM-AS-EMPLOYER
   The sender domain is an ATS/relay platform (SuccessFactors, Workday, Oracle,
   Greenhouse), so the *registrable domain is the platform, not the employer*.
   Naively naming the company after the domain yields "Successfactors".
   -> RESOLUTION: never take the company from an ATS/relay domain. Recover the
      employer, in order, from: the sender display name (including an embedded
      `HR@employer.com`), a subject pattern ("...applying to <Company>"), or a
      body signal (a Workday careers-URL tenant, `<employer>.wdN.myworkdayjobs`).

3. PLATFORM-TOKEN CONTAMINATION
   Workday (and peers) append the platform name to the sender display, e.g.
   `from_name = "NCR Voyix Workday"`, gluing "Workday" onto the employer.
   -> RESOLUTION: strip a trailing ATS/HR platform token from the parsed company.

The ANCHOR cases are real application mail that MUST stay + parse, so a future
"drop harder" change cannot silently start discarding genuine confirmations.
"""
import pytest

from jobscope.ingest import mailrules

_BODY_BAYER = (
    "Hello Mohit, You\u2019ve applied for the position of Cyber Security Engineer "
    "with Bayer. We will review your application carefully and get in touch soon."
)
_BODY_MIMECAST = (
    "Hi Mohit, Thank you for taking the time to apply for the R6521 Associate "
    "Threat Response Analyst role. https://mimecast.wd5.myworkdayjobs.com/Mimecast-Careers"
)

# Failure mode 1 -- dropped by sender domain regardless of any strong signal.
#   id, from_name, from_domain, subject, body
DROP_CASES = [
    ("eatclub-food-receipt", "Eatclub", "eatclub.in",
     "Eatclub Confirmation - You have successfully paid online for your order", ""),
    ("thinkific-course-assessment", "PURSUIT Academy", "notify.thinkific.com",
     "You are now enrolled in PURSUIT - Volunteer Training & Assessment!", ""),
    ("leetcode-interview-promo", "LeetCode", "leetcode.com",
     "Ace your next interview with LeetCode's Interview Crash Course", ""),
]

# Failure modes 2 & 3 -- the employer must win over the ATS/relay platform.
#   id, from_name, from_domain, subject, body, expected_company
COMPANY_CASES = [
    ("bayer-successfactors-eu-relay", "HR@Bayer.com", "successfactors.eu",
     "Thank you for your application", _BODY_BAYER, "Bayer"),
    ("ncr-voyix-workday-token", "NCR Voyix Workday", "myworkday.com",
     "Thank You for Your Application!", "", "NCR Voyix"),
    ("mimecast-workday-tenant-url", "", "myworkday.com",
     "Thanks for your application!", _BODY_MIMECAST, "Mimecast"),
]

# Anchors -- genuine application mail that must never be dropped or mis-named.
#   id, from_name, from_domain, subject, body, expected_company
ANCHOR_CASES = [
    ("greenhouse-deepwatch", "", "us.greenhouse-mail.io",
     "Thank you for applying to Deepwatch India", "", "Deepwatch India"),
    ("lever-drivetrain", "Drivetrain", "hire.lever.co",
     "Thank you for your application to Drivetrain", "", "Drivetrain"),
]

# Failure mode 4 -- SIGNAL false positive: the FUNNEL SIGNAL is wrong even though
# the sender + company parse fine. The recurring case is a live "interview" tag on
# mail that only *mentions* an interview ("our interview process"), *promises a
# future* one ("we'll be in touch to schedule an interview"), phrases it as a
# *hypothetical* ("if selected, we'll invite you to interview"), or carries soft
# recruiter boilerplate ("I'd like to chat"). A real interview is positively
# invited / scheduled / named / advanced; anything else is the confirmation,
# recruiter note, or rejection it really is.
#   id, subject, body, expected_signal
SIGNAL_CASES = [
    # -- genuine interviews: an invite/schedule/modality/advancement is asserted --
    ("interview-invite-phone", "Interview invitation \u2014 Security Engineer at Acme",
     "Hi Mohit, we were impressed by your application and would like to invite you to a "
     "phone interview. Could you share your availability this week?", "interview"),
    ("interview-schedule-video", "Next steps with Acme",
     "We'd like to schedule a video interview with the hiring manager. Are you free "
     "Tuesday or Wednesday afternoon?", "interview"),
    ("interview-calendly-selfbook", "Let's find time to talk",
     "Thanks for your patience! Please grab whatever slot works for you here: "
     "https://calendly.com/acme-talent/screen", "interview"),
    ("interview-onsite-final-round", "Final round: onsite interview",
     "Congratulations on reaching the final round. We'd like to arrange an onsite "
     "interview at our London office next week.", "interview"),
    ("interview-availability-generic-subject", "Your application to Acme",
     "We reviewed your application and want to move forward. Please share your "
     "availability for a 30-minute call with the team.", "interview"),
    # -- other genuine signals stay put --
    ("assessment-online-oa", "Coding assessment \u2014 Acme",
     "Please complete the online coding assessment within 3 days via HackerRank.", "assessment"),
    ("offer-clear", "Your offer from Acme",
     "We are pleased to offer you the position of Security Engineer.", "offer"),
    ("rejection-clear", "Update on your application",
     "Unfortunately, we have decided not to move forward with your application at this time.",
     "rejection"),
    ("rejection-after-interview", "Your application to Acme",
     "Thank you for taking the time to interview with our team. After careful "
     "consideration, we've decided to move forward with other candidates.", "rejection"),
    ("confirmation-clean", "Thank you for applying to Acme",
     "We've received your application for the Security Engineer role and will review it.",
     "confirmation"),
    # -- THE BUG: interview merely mentioned / promised / hypothetical / soft --
    ("ack-hypothetical-interview", "Update from the Acme talent team",
     "Thank you for applying to Acme. If your background matches an opening, a recruiter "
     "will reach out to schedule an interview.", "confirmation"),
    ("ack-future-interview-promise", "Update from the Acme talent team",
     "Thanks for applying! Our team will reach out to schedule an interview and share "
     "next steps soon.", "confirmation"),
    ("ack-interview-process-described", "What to expect after applying to Acme",
     "Thank you for applying. Our interview process has three stages, and we'll let you "
     "know about next steps.", "confirmation"),
    ("ack-next-steps-generic-subject", "Next steps in your Acme application",
     "Thanks for applying. We'll review your profile and be in touch about next steps.",
     "confirmation"),
    ("recruiter-soft-chat", "Opportunity at Acme",
     "I came across your LinkedIn profile and would like to chat about a Security "
     "Engineer role on our team.", "recruiter"),
    ("content-interview-tips-not-funnel", "5 tips to ace your next interview",
     "Prepare for your upcoming interview with these tips from our blog.", "other"),
]

_PLATFORM_NAMES = {"successfactors", "workday", "myworkday", "greenhouse", "lever",
                   "icims", "taleo", "oracle"}


@pytest.mark.parametrize(
    "cid,from_name,domain,subject,body", DROP_CASES, ids=[c[0] for c in DROP_CASES]
)
def test_fp_non_job_sender_is_dropped(cid, from_name, domain, subject, body):
    # Mode 1: the sender domain is a hard drop, so no signal it scores can leak in.
    assert mailrules.is_newsletter_domain(domain) is True


@pytest.mark.parametrize(
    "cid,from_name,domain,subject,body,expected", COMPANY_CASES,
    ids=[c[0] for c in COMPANY_CASES],
)
def test_fp_employer_wins_over_platform(cid, from_name, domain, subject, body, expected):
    # Modes 2 & 3: recover the employer; never surface the ATS/relay platform.
    company, _role = mailrules.parse_company_role(from_name, domain, subject, body)
    assert company == expected
    assert company.lower() not in _PLATFORM_NAMES


@pytest.mark.parametrize(
    "cid,from_name,domain,subject,body,expected", ANCHOR_CASES,
    ids=[c[0] for c in ANCHOR_CASES],
)
def test_fp_anchor_real_application_survives(cid, from_name, domain, subject, body, expected):
    # Guardrail: real application mail is kept (not a drop domain) and named right.
    assert mailrules.is_newsletter_domain(domain) is False
    company, _role = mailrules.parse_company_role(from_name, domain, subject, body)
    assert company == expected


@pytest.mark.parametrize(
    "cid,subject,body,expected", SIGNAL_CASES, ids=[c[0] for c in SIGNAL_CASES]
)
def test_fp_signal_is_classified_correctly(cid, subject, body, expected):
    # Mode 4: the deterministic funnel signal. A real interview must be positively
    # invited/scheduled/named -- a mention, promise, hypothetical, or soft chat is
    # the confirmation / recruiter note / rejection it really is.
    assert mailrules.classify_scored(subject, body)[0] == expected
