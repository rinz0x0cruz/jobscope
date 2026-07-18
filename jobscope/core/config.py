"""Configuration loading for jobscope.

A single ``DEFAULT_CONFIG`` dict is deep-merged with an optional user file
(``config.yaml`` or ``config.json``). Secrets are never stored in the config
file; they are read from environment variables (optionally via a ``.env`` file).
"""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "profile": {
        "resume_path": "data/resume.md",
        "primary_resume": "",
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "links": {},
    },
    "search": {
        "sites": ["indeed", "linkedin", "google"],
        "terms": ["software engineer"],
        "google_term": "",
        "location": "Remote",
        "country_indeed": "India",
        "results_wanted": 25,
        "hours_old": 168,
        "is_remote": True,
        "distance": 50,
        "linkedin_fetch_description": True,
        "proxies": [],
        "profiles": [],
        "companies": [],
        "home_country": "India",   # geo scope: the country you can work onsite in (see core.geo)
        "scope_to_home": True,     # drop roles outside {home onsite, global/home-eligible remote}
    },
    "discovery": {
        "enabled": True,
        "interval_hours": 24,
    },
    "match": {
        "weights": {
            "skills": 0.34,
            "title": 0.18,
            "seniority": 0.12,
            "comp": 0.10,
            "location": 0.10,
            "recency": 0.04,
            "company": 0.12,
        },
        "min_salary": 0,
        "target_seniority": "",   # "" = infer from resume; else junior/mid/senior... (down-ranks roles above it)
        "ai_seniority_tiebreak": True,   # if ai.enabled: AI-classify ambiguous non-Skip postings
        "ai_tiebreak_max_calls": 0,      # 0 = unbounded; else cap AI classify calls per match run
        # Optional multi-model second opinion on jobs near a tier cut (off by default;
        # needs quorum.enabled). CLI-only: never changes the deterministic score/tier.
        "ai_score_review": False,
        "ai_score_margin": 8,            # review jobs within this many points of a tier cut
        "ai_score_max_calls": 12,        # 0 = unbounded; else cap judge calls per match run
        "prefer_locations": [],
        "prefer_companies": [],
        "prefer_company_size": "any",
        "tiers": {"strong": 75, "good": 55, "stretch": 35},
        "ghost_penalty": 15,
        "remote_scope_strict": False,
    },
    "filters": {
        "needs_sponsorship": False,
        "exclude_clearance": False,
        "block_companies": [],
        "block_keywords": [],
        "block_title_keywords": [],
        "require_title_keywords": [],  # allow-list: if set, a title matching none is filtered to Skip
        "max_age_days": 0,
        "stale_days": 45,  # badge (not drop) postings older than N days as likely-stale/ghost; 0 = off
        "max_years_experience": 0,
    },
    "enrich": {
        "compensation": True,
        "stock": True,
        "reddit": True,
        "news": True,
        "glassdoor": True,
        "contacts": True,
        "brief": True,
        "news_feeds": [],
        "top_n": 10,
    },
    "ai": {
        "enabled": False,
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "temperature": 0.3,
        "max_tokens": 1200,
        "api_key_env": "JOBSCOPE_AI_API_KEY",
    },
    # Optional: route the AI layer through a quorum deliberation (multi-model or
    # self-refine) instead of one model. Off by default; needs the `quorum`
    # package installed (github.com/rinz0x0cruz/quorum).
    "quorum": {
        "enabled": False,      # true + ai.enabled + key -> deliberate instead of single-shot
        "strategy": "refine",  # default: refine | debate | council | moa | ensemble
        # Per-task overrides (only used when quorum.enabled). Empty -> use `strategy`.
        "strategy_generative": "council",  # summary / cover letter / "why here" (higher quality)
        "strategy_classify": "ensemble",   # seniority / email labels (self-consistency vote)
        "rate_limit_rpm": 18,  # pace below OpenRouter's 20 RPM free ceiling
        "fallbacks": [         # exact refs only; never a random free router
            "openrouter:google/gemma-4-26b-a4b-it:free",
            "openrouter:nvidia/nemotron-3-super-120b-a12b:free",
        ],
    },
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "from_addr": "",
        "to_addr": "",
        "password_env": "JOBSCOPE_SMTP_PASSWORD",
    },
    # Optional: monitor Gmail inbox(es) over read-only IMAP for the application
    # process (confirmations / rejections / interviews / offers) and feed the
    # funnel. App passwords live in the environment, referenced by name here.
    "inbox": {
        "enabled": False,
        "accounts": [],          # [{email: "you@gmail.com", password_env: "JOBSCOPE_GMAIL_APP_PW"}]
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "folder": "INBOX",
        "include_spam": False,   # also sweep the spam folder -- a real application email misfiled as spam is still caught
        "spam_folder": "[Gmail]/Spam",  # Gmail's IMAP spam folder (localize if your account isn't English)
        "lookback_days": 90,     # first run scans this far back; later runs are incremental
        "uid_recovery_days": 30, # bounded replay if Gmail resets the folder's UIDVALIDITY epoch
        "imap_attempts": 3,      # reconnect on transient IMAP abort/network failures
        "classification_chars": 6000, # body text inspected in memory; stored snippets remain <=500 chars
        "store_snippets": False, # persist a short email-body excerpt? off = classify in memory then discard (less PII at rest)
    },
    "apply": {
        "assist": False,
        "package_dir": "data/applications",
        "auto_prep_top": 3,
        "followup_days": 7,
        # Opt-in recruiter outreach (`jobscope outreach <job_id>`). Preview-only by
        # default; sending needs enabled + email.* configured + --send, is deduped
        # per company with a cooldown, and never mass-mails or guesses addresses.
        "outreach": {
            "enabled": False,
            "discover": True,
            "role_inboxes": ["careers", "jobs", "recruiting", "talent", "hr"],
            "cooldown_days": 14,
            "do_not_contact": [],
            # Optional third-party HR-email finder (opt-in). API keys are read from
            # these ENV VARS -- never stored in config; unset -> finder off and the
            # deterministic on-site discovery still runs.
            "finder": {
                "hunter_key_env": "JOBSCOPE_HUNTER_API_KEY",
                "apollo_key_env": "JOBSCOPE_APOLLO_API_KEY",
            },
            # Pre-compute HR contacts for your most-recent ACTIVE applications each
            # refresh (excludes rejected/offer/closed), so they show on the published
            # dashboard behind unlock. Re-discovered at most once per max_age_days.
            "applied_scan": {
                "limit": 25,
                "max_age_days": 14,
            },
            # Targeted company scans also refresh a verified recruiter/HR contact.
            # Scheduled all-company scans reuse fresh contacts to bound network work.
            "monitor_scan": {
                "enabled": True,
                "max_age_days": 14,
                "scheduled": False,
            },
            # Local-only, individually approved cold-outreach campaigns. Ranking
            # and drafting are safe while outreach is disabled; SMTP still needs
            # both outreach.enabled and email.enabled.
            "campaign": {
                "weights": {"region": 0.50, "compensation": 0.30, "growth": 0.20},
                "include_default_pool": True,
                "curated_companies": [],
                "company_overrides": {},
                "daily_limit": 2,
                "min_spacing_hours": 4,
                "timezone": "Asia/Kolkata",
                "send_window_start": "10:00",
                "send_window_end": "17:00",
            },
        },
    },
    "output": {
        "db_path": "data/jobscope.db",
        "include_skip": False,  # publish Skip-tier (off-target/too-senior) roles to the dashboard? default: hide them
    },
    "retention": {
        "reconciliation_audit_days": 730,
    },
    # Local dashboard control plane (`jobscope serve`). Reads current SQLite data
    # and can sync Gmail + rescore without rebuilding or publishing.
    "serve": {
        "refresh_enabled": True,     # show/allow the local Gmail refresh button
        "refresh_full_scan": False,  # also re-scrape job boards (429-prone) before matching
        "inbox_days": 7,             # Gmail lookback window for the button's inbox sync
        "build_on_start": False,     # rebuild the SPA when `serve` starts (else serve the last build)
        "web_dist": None,            # override the served SPA dir (default: <repo>/web/dist)
    },
}

CONFIG_CANDIDATES = ("config.yaml", "config.yml", "config.json")


def _deep_merge(base: dict, override: dict) -> dict:
    import copy
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def _parse_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        if path.endswith(".json"):
            return json.load(fh)
        try:
            import yaml  # lazy: only needed for YAML configs
        except ImportError as exc:  # pragma: no cover - guidance path
            raise SystemExit(
                "PyYAML is required to read YAML config. Install with "
                "`pip install pyyaml`, or use config.json instead."
            ) from exc
        return yaml.safe_load(fh) or {}


def load_config(path: str | None = None) -> dict[str, Any]:
    """Return the effective config (defaults deep-merged with a user file)."""
    _load_dotenv()
    if path is None:
        for candidate in CONFIG_CANDIDATES:
            if os.path.exists(candidate):
                path = candidate
                break
    if path and os.path.exists(path):
        return _deep_merge(DEFAULT_CONFIG, _parse_file(path))
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy


KEYRING_SERVICE = "jobscope"


def _secret(name: str, default: str = "") -> str:
    """Resolve a secret referenced by env-var NAME, keychain-first.

    Order: the OS keychain (Windows Credential Manager / macOS Keychain / Secret
    Service, via the optional ``keyring`` package) then the process environment
    (real env or ``.env``). Keyring is optional and best-effort -- if it isn't
    installed or has no backend, we silently fall back to the environment so the
    tool stays portable. Secrets are never read from the config file itself.
    """
    if not name:
        return default
    try:
        import keyring  # optional dependency
        val = keyring.get_password(KEYRING_SERVICE, name)
        if val:
            return val
    except Exception:  # noqa: BLE001 - keyring missing / no backend -> env fallback
        pass
    return os.environ.get(name, default)


def api_key(cfg: dict) -> str:
    return _secret(cfg.get("ai", {}).get("api_key_env", "JOBSCOPE_AI_API_KEY"))


def smtp_password(cfg: dict) -> str:
    return _secret(cfg.get("email", {}).get("password_env", "JOBSCOPE_SMTP_PASSWORD"))


def inbox_password(cfg: dict, account: dict) -> str:
    """Return the Gmail app password for an inbox account, referenced by the env-var
    name in that account's ``password_env`` and resolved keychain-first (never stored
    in the config file)."""
    env = (account or {}).get("password_env", "")
    return _secret(env) if env else ""
