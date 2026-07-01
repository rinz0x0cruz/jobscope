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
        "country_indeed": "USA",
        "results_wanted": 25,
        "hours_old": 168,
        "is_remote": True,
        "distance": 50,
        "linkedin_fetch_description": True,
        "proxies": [],
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
        "seniority": "mid",
        "prefer_locations": [],
        "prefer_companies": [],
        "tiers": {"strong": 75, "good": 55, "stretch": 35},
        "ghost_penalty": 15,
    },
    "filters": {
        "needs_sponsorship": False,
        "exclude_clearance": False,
        "block_companies": [],
        "block_keywords": [],
        "block_title_keywords": [],
        "max_age_days": 0,
    },
    "enrich": {
        "compensation": True,
        "stock": True,
        "reddit": True,
        "news": True,
        "glassdoor": False,
        "contacts": True,
        "brief": True,
        "news_feeds": [],
        "top_n": 10,
    },
    "ai": {
        "enabled": False,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "max_tokens": 1200,
        "api_key_env": "JOBSCOPE_AI_API_KEY",
    },
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "from_addr": "",
        "to_addr": "",
        "password_env": "JOBSCOPE_SMTP_PASSWORD",
    },
    "apply": {
        "assist": False,
        "package_dir": "data/applications",
        "auto_prep_top": 3,
        "followup_days": 7,
    },
    "output": {
        "db_path": "data/jobscope.db",
        "dashboard_path": "data/dashboard.html",
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


def api_key(cfg: dict) -> str:
    return os.environ.get(cfg.get("ai", {}).get("api_key_env", "JOBSCOPE_AI_API_KEY"), "")


def smtp_password(cfg: dict) -> str:
    return os.environ.get(cfg.get("email", {}).get("password_env", "JOBSCOPE_SMTP_PASSWORD"), "")
