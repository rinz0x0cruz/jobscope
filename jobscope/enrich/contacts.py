"""Referral-lead discovery -- legit-only.

No private-profile scraping and no email harvesting. We hand back:
  * ready-made LinkedIn / Google *search* links (company + role, and recruiters), and
  * real public GitHub profiles that list the company (public API),
each with a deterministic outreach draft (AI can rewrite it in Phase 3).
"""
from __future__ import annotations

import hashlib
import os
from urllib.parse import quote_plus

from ..model import Contact
from .. import httpx

GH_SEARCH = "https://api.github.com/search/users"


def find(company: str, job) -> list[Contact]:
    role = (getattr(job, "title", "") or "").strip()
    leads: list[Contact] = []

    # 1) Search links (always available, zero risk)
    ln_people = ("https://www.linkedin.com/search/results/people/?keywords="
                 + quote_plus(f"{company} {role}"))
    ln_recruiter = ("https://www.linkedin.com/search/results/people/?keywords="
                    + quote_plus(f"{company} recruiter talent"))
    google = ("https://www.google.com/search?q="
              + quote_plus(f'site:linkedin.com/in "{company}" ({role} OR recruiter)'))
    leads.append(_lead(company, "Find the team on LinkedIn", role, "linkedin-search",
                       search_url=ln_people))
    leads.append(_lead(company, "Find a recruiter on LinkedIn", "Recruiter", "linkedin-search",
                       search_url=ln_recruiter))
    leads.append(_lead(company, "Find people via Google", role, "google-search",
                       search_url=google))

    # 2) Real public GitHub profiles that list this company
    leads.extend(_github_people(company, role))
    return leads


def _github_people(company: str, role: str) -> list[Contact]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = httpx.get_json(
        GH_SEARCH,
        params={"q": f'"{company}" in:company', "per_page": 5},
        headers=headers,
    )
    out: list[Contact] = []
    if not payload:
        return out
    for u in payload.get("items", [])[:5]:
        login = u.get("login", "")
        if not login:
            continue
        profile = httpx.get_json(f"https://api.github.com/users/{login}", headers=headers) or {}
        name = profile.get("name") or login
        bio = (profile.get("bio") or "").strip()
        # only keep profiles that actually reference the company
        blob = f"{profile.get('company','')} {bio}".lower()
        if company.lower() not in blob:
            continue
        out.append(_lead(company, name, bio or role, "github",
                         profile_url=profile.get("html_url", u.get("html_url", ""))))
    return out


def _lead(company: str, name: str, title: str, source: str,
          profile_url: str = "", search_url: str = "") -> Contact:
    key = hashlib.sha1(f"{company}|{source}|{profile_url or name}".encode()).hexdigest()[:16]
    return Contact(
        id=key,
        company=company,
        name=name,
        title=title,
        source=source,
        profile_url=profile_url,
        search_url=search_url,
        outreach=_draft(company, name, source),
    )


def _draft(company: str, name: str, source: str) -> str:
    if source.endswith("search"):
        return ""  # search links don't need an outreach message
    first = name.split()[0] if name and name[0].isalpha() else "there"
    return (
        f"Hi {first}, I came across your profile while researching {company}. "
        f"I'm exploring a role there and would love a quick perspective on the team "
        f"(or a referral, if you're open to it). Happy to share my background -- thanks!"
    )
