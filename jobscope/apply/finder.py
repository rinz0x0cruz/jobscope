"""Optional third-party HR-email finders (Hunter.io + Apollo).

Opt-in and best-effort: each provider is used only when its API key is present in
the configured environment variable, and any network/parse failure returns ``[]``
-- so the deterministic on-site discovery always stands on its own. Keys are read
from the environment (never stored in config, never logged), and every returned
address is validated to be a real, non-automated address on the company's domain.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from jobscope.core import httpx

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_AUTOMATED = ("noreply", "no-reply", "donotreply", "do-not-reply", "notification",
              "notifications", "mailer-daemon", "postmaster", "bounce", "no_reply")


def _key(cfg: dict, name_key: str, default_env: str) -> str:
    """Resolve an API key from the ENV VAR named in config (never a raw key in config)."""
    finder = (cfg.get("apply", {}).get("outreach", {}).get("finder", {}) or {})
    env = (finder.get(name_key) or default_env or "").strip()
    return (os.environ.get(env, "") or "").strip() if env else ""


def _valid(email: str, domain: str) -> bool:
    """A real, non-automated address on the resolved company domain."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return False
    local, dom = email.split("@", 1)
    if any(a in local for a in _AUTOMATED):
        return False
    d = domain.lower()
    return dom == d or dom.endswith("." + d)


def _hunter(cfg: dict, domain: str) -> list[dict]:
    key = _key(cfg, "hunter_key_env", "JOBSCOPE_HUNTER_API_KEY")
    if not key or not domain:
        return []
    data = httpx.get_json(
        "https://api.hunter.io/v2/domain-search",
        params={"domain": domain, "api_key": key, "department": "hr,management", "limit": 10})
    emails = (((data or {}).get("data") or {}).get("emails")) or []
    out: list[dict] = []
    for e in emails:
        addr = (e.get("value") or "").strip().lower()
        if not _valid(addr, domain):
            continue
        score = e.get("confidence") or 0
        name = " ".join(
            part for part in (e.get("first_name"), e.get("last_name")) if part
        ).strip()
        title = (e.get("position") or "recruiting contact").strip()
        identity = " · ".join(part for part in (name, title) if part)
        out.append({"email": addr, "confidence": "high" if score >= 80 else "medium",
                    "source": "hunter", "note": f"{identity} via Hunter.io"})
    return out


def _post_json(url: str, body: dict, headers: Optional[dict] = None) -> Optional[dict]:
    try:
        import requests
        h = {"User-Agent": httpx.USER_AGENT, "Content-Type": "application/json",
             "Accept": "application/json", **(headers or {})}
        resp = requests.post(url, json=body, headers=h, timeout=httpx.DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:  # noqa: BLE001 - best-effort
        return None
    return None


def _apollo(cfg: dict, domain: str) -> list[dict]:
    key = _key(cfg, "apollo_key_env", "JOBSCOPE_APOLLO_API_KEY")
    if not key or not domain:
        return []
    # Apollo people search (POST). People carry an email only when the account/plan
    # reveals it; we take whatever real, on-domain addresses come back and never guess.
    resp = _post_json(
        "https://api.apollo.io/v1/mixed_people/search",
        {"q_organization_domains": domain,
         "person_titles": [
             "cybersecurity recruiter", "security recruiter", "technical recruiter",
             "engineering recruiter", "technical talent acquisition",
             "talent acquisition partner", "recruiter", "hiring manager",
         ],
         "page": 1, "per_page": 10},
        headers={"X-Api-Key": key})
    people = (resp or {}).get("people") or []
    out: list[dict] = []
    for p in people:
        addr = (p.get("email") or "").strip().lower()
        if not _valid(addr, domain):
            continue
        title = (p.get("title") or "contact").strip()
        out.append({"email": addr, "confidence": "medium", "source": "apollo",
                    "note": f"{title} via Apollo"})
    return out


def find_contacts(cfg: dict, company: str, domain: str) -> list[dict]:
    """HR contacts from the opt-in finders (Hunter.io + Apollo). Returns ``[]`` unless
    a provider key is configured; results are deduped and on-domain, never fabricated."""
    found: list[dict] = []
    try:
        found += _hunter(cfg, domain)
    except Exception:  # noqa: BLE001 - one provider never breaks the other
        pass
    try:
        found += _apollo(cfg, domain)
    except Exception:  # noqa: BLE001
        pass
    rank = {"high": 0, "medium": 1, "low": 2}
    best: dict[str, dict] = {}
    for c in found:
        e = c["email"]
        if e not in best or rank.get(c["confidence"], 3) < rank.get(best[e]["confidence"], 3):
            best[e] = c
    return list(best.values())
