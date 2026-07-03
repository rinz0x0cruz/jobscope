"""Deterministic job-fit scoring (the core "80% logic").

``score_job`` returns a transparent 0-100 score plus a tier and a short rationale,
computed only from the resume and the posting -- no network, no AI. Weights are
configurable (see config `match.weights`). A scam/ghost-job penalty mirrors the
idea behind career-ops' "Block G" legitimacy check.

The implementation is split by concern into this package, layered so the leaves
never import back up:

* :mod:`.seniority` -- ``SENIORITY_RANK`` + title/level/numeric inference and the
  asymmetric seniority fit score (leaf; imports only the model);
* :mod:`.experience` -- ``required_experience_years`` (depends on seniority);
* :mod:`.filters` -- block-lists, clearance/sponsorship + ghost detectors and
  ``apply_filters`` (depends on experience);
* :mod:`.scoring` -- ``score_job`` and its skill/title/comp/location/company/
  recency sub-scores and tiering (depends on seniority + filters);
* :mod:`.routing` -- ``select_base`` résumé routing (depends on scoring);
* :mod:`.run` -- the ``run`` orchestrator (lazily uses ``ai``/``classify``).

The public surface is unchanged: ``from jobscope.match import score_job`` -- and
every other name below, including the private helpers and signal lists the tests
and selftest import -- keeps working exactly as it did from the flat module.
"""
from __future__ import annotations

from .experience import _SENIORITY_MIN_YEARS, required_experience_years
from .filters import (
    CLEARANCE_SIGNALS,
    GHOST_SIGNALS,
    NO_SPONSORSHIP_SIGNALS,
    _age_days,
    apply_filters,
    clearance_flags,
    ghost_flags,
    no_sponsorship,
)
from .routing import (
    ADVISORY_SIGNALS,
    DISCIPLINE_SELECT_WEIGHT,
    LEAN_DECISIVE,
    TECHNICAL_SIGNALS,
    _job_lean,
    _lean,
    _lean_counts,
    _resume_lean,
    select_base,
)
from .run import run
from .scoring import (
    _TOKEN_RE,
    SKILL_TARGET,
    _comp_score,
    _company_score,
    _location_score,
    _rationale,
    _recency_score,
    _size_signal,
    _skill_score,
    _title_score,
    _tokens,
    score_job,
)
from .seniority import (
    _JOB_LEVEL_RANK,
    _NUMERIC_LEVEL,
    SENIORITY_RANK,
    _job_seniority,
    _seniority_score,
    _title_seniority,
)

__all__ = [
    # constants
    "SENIORITY_RANK",
    "SKILL_TARGET",
    "_TOKEN_RE",
    "GHOST_SIGNALS",
    "CLEARANCE_SIGNALS",
    "NO_SPONSORSHIP_SIGNALS",
    "TECHNICAL_SIGNALS",
    "ADVISORY_SIGNALS",
    "_JOB_LEVEL_RANK",
    "_NUMERIC_LEVEL",
    "_SENIORITY_MIN_YEARS",
    "DISCIPLINE_SELECT_WEIGHT",
    "LEAN_DECISIVE",
    # seniority
    "_title_seniority",
    "_job_seniority",
    "_seniority_score",
    # experience
    "required_experience_years",
    # filters + legitimacy
    "ghost_flags",
    "clearance_flags",
    "no_sponsorship",
    "_age_days",
    "apply_filters",
    # scoring
    "_tokens",
    "_skill_score",
    "_title_score",
    "_comp_score",
    "_location_score",
    "_size_signal",
    "_company_score",
    "_recency_score",
    "score_job",
    "_rationale",
    # routing
    "_lean_counts",
    "_lean",
    "_resume_lean",
    "_job_lean",
    "select_base",
    # orchestrator
    "run",
]
