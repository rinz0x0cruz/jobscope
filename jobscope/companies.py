"""Offline, curated company-prestige tiers for ranking (deterministic, no network).

Used by `match._company_score` to prioritize well-known / high-quality employers.
Matching is token-subset based (a known name's tokens must all appear in the
company name) so "Meta" matches "Meta Platforms" but not "Metabase". Edit freely.
"""
from __future__ import annotations

import re

_SUFFIX = {"inc", "llc", "ltd", "corp", "corporation", "co", "plc", "group", "holdings",
           "technologies", "technology", "labs", "lab", "software", "systems", "solutions",
           "the", "company", "limited", "gmbh", "srl", "sa", "ag", "pvt", "private"}

# Tier 1 -- elite (unambiguous single tokens are safe here).
ELITE = ["google", "alphabet", "meta", "facebook", "apple", "amazon", "microsoft",
         "netflix", "nvidia", "openai", "anthropic"]

# Tier 2 -- top tech + top security (multi-word names preferred to avoid false hits).
TOP = ["tesla", "salesforce", "adobe", "oracle", "sap", "intel", "qualcomm", "cisco",
       "vmware", "broadcom", "airbnb", "stripe", "databricks", "snowflake", "atlassian",
       "shopify", "spotify", "linkedin", "paypal", "coinbase", "palantir", "servicenow",
       "workday", "twilio", "cloudflare", "datadog", "mongodb", "gitlab", "github",
       "dropbox", "pinterest", "doordash", "robinhood", "roblox", "twitch"]
SECURITY = ["palo alto networks", "crowdstrike", "zscaler", "fortinet", "okta", "wiz",
            "sentinelone", "tenable", "rapid7", "check point", "cyberark", "snyk", "splunk",
            "mandiant", "darktrace", "arctic wolf", "orca security", "aqua security", "sysdig",
            "lacework", "hashicorp", "elastic", "proofpoint", "sailpoint", "varonis",
            "netskope", "abnormal security", "semgrep", "sonarsource", "1password"]

# Tier 3 -- notable / strong startups & unicorns.
NOTABLE = ["revolut", "plaid", "notion", "figma", "canva", "discord", "reddit", "brex",
           "retool", "vercel", "netlify", "grafana", "temporal", "confluent",
           "cockroach labs", "airtable", "miro", "monzo", "affirm", "rippling", "anduril",
           "scale ai", "hugging face", "cohere", "mistral", "perplexity"]

_TIERS = [(1.00, "elite", ELITE), (0.90, "top", TOP + SECURITY), (0.75, "notable", NOTABLE)]


def _tokens(s: str) -> set[str]:
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return {t for t in s.split() if t and t not in _SUFFIX}


_COMPILED = [(score, label, [_tokens(n) for n in names]) for score, label, names in _TIERS]


def company_quality(company: str) -> tuple[float, str]:
    """Return (score 0-1, tier_label). Unknown companies get a neutral 0.5."""
    ct = _tokens(company)
    if not ct:
        return 0.5, ""
    for score, label, namesets in _COMPILED:
        for ns in namesets:
            if ns and ns <= ct:
                return score, label
    return 0.5, ""
