# jobscope — feature backlog

Ideas surfaced by scanning similar open-source projects and community outlets on 2026-07-07, filtered to what fits jobscope's ethos (deterministic-first, local/private, single-user, leverages data already collected — Gmail→funnel, `mail_events`, scoring, enrichment, encrypted applications, PWA dashboard).

Each item has a tracking issue. Repo issues: <https://github.com/rinz0x0cruz/jobscope/issues>

## Recommended starter set

These four ride entirely on data jobscope already collects, land in the dashboard/backend already shipped, and hit the loudest community pain points — no new scraping, no accounts, stays local.

| # | Feature | Why it's first | Effort |
|---|---------|----------------|--------|
| [#27](https://github.com/rinz0x0cruz/jobscope/issues/27) | Ghosted / stale application detection | ~a third of applications end in "no reply"; the data (`mail_events`) is already there | Low |
| [#28](https://github.com/rinz0x0cruz/jobscope/issues/28) | Conversion & response analytics | Turns the funnel from counts into effectiveness (rates, time-in-stage) | Med |
| [#29](https://github.com/rinz0x0cruz/jobscope/issues/29) | Follow-ups-due panel + reminders | `apply.followup_days` already in config — just surface it | Low |
| [#30](https://github.com/rinz0x0cruz/jobscope/issues/30) | Archive the full JD (snapshot) | Listings vanish right before interviews | Med |

## Differentiators (deterministic-friendly, less common in the field)

| # | Feature | Source | Effort |
|---|---------|--------|--------|
| [#31](https://github.com/rinz0x0cruz/jobscope/issues/31) | ATS parse check + JD keyword coverage | Medium ("parser quietly deleted half of it"), Huntr | Med |
| [#32](https://github.com/rinz0x0cruz/jobscope/issues/32) | Semantic JD↔resume coverage (responsibilities, not keywords) | Huntr | Med-High |
| [#33](https://github.com/rinz0x0cruz/jobscope/issues/33) | Per-application interview prep hub (brief + notes + STAR) | Grindstone, Job-Copilot | Med |

## Lighter / optional

| # | Feature | Source | Effort |
|---|---------|--------|--------|
| [#26](https://github.com/rinz0x0cruz/jobscope/issues/26) | New-match digest (email/notify on scheduled scan) | commandjobs, apply-potato | Low-Med |
| [#34](https://github.com/rinz0x0cruz/jobscope/issues/34) | Surface referral paths + draft outreach | Job-Copilot | Low |
| [#35](https://github.com/rinz0x0cruz/jobscope/issues/35) | Grab-bag: gamification/velocity, "Chances" score, A–F grading, shareable Sankey | Medium (8-8-8), ApplyFlow, career-ops, Rolepad | Low each |

## Sources scanned

- **GitHub** topics `job-search` / `job-application-tracker` (17+ OSS): career-ops, job-ops, JobNavigator, Jobtra, JobMatchAI, jobsync, Job-Copilot, apply-potato, commandjobs, JobFunnel, JobSpy, and more.
- **Hacker News** Show/Ask: Rolepad, RunMagi, Grindstone, ApplyFlow, TrackJ, Huntr, "Biggest pain point in your job search?".
- **dev.to** `#jobsearch`, **Medium** `job-hunting` feed (ATS parsing, tailoring, follow-up timing, gamification).
- **Reddit** r/recruitinghell, r/jobsearch (ghosting, application volume, tailoring fatigue).

## Notably NOT pursued (off-ethos for jobscope)

- Browser extension / one-click ATS autofill (heavier, privacy surface; jobscope is scrape + local).
- Accounts / multi-user / employer-side features (Rolepad's two-sided model).
- Cloud SaaS storage (jobscope keeps data local + encrypted).
