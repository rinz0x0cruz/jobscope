"""Offline, curated company-prestige and company-size tiers for ranking.

Deterministic and network-free. `company_quality` powers a prestige signal and
`company_size` powers a headcount signal; both are consumed by
`match._company_score`. Matching is token-subset based (a known name's tokens
must all appear in the company name) so "Meta" matches "Meta Platforms" but not
"Metabase". Edit the lists freely.
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


# --- company size (headcount) tiers ---------------------------------------
# Approximate employee bands for well-known employers. Used by
# `match._company_score` when `prefer_company_size` is set. Sizes drift as
# companies grow; this is a best-effort ranking aid, not ground truth.
_MEGA = ["amazon", "microsoft", "apple", "google", "alphabet", "oracle", "intel",
         "ibm", "cisco", "sap", "dell", "samsung", "sony", "siemens", "bosch",
         "accenture", "deloitte", "capgemini", "cognizant", "infosys", "wipro",
         "tcs", "tata consultancy services", "hcltech", "tech mahindra",
         "jpmorgan", "bank of america", "wells fargo", "citigroup", "comcast",
         "verizon", "walmart", "boeing", "lockheed martin", "honeywell"]
_LARGE = ["meta", "facebook", "nvidia", "salesforce", "adobe", "qualcomm",
          "broadcom", "vmware", "netflix", "paypal", "servicenow", "workday",
          "tesla", "uber", "linkedin", "autodesk", "intuit", "ebay", "amd",
          "micron", "visa", "mastercard", "ericsson", "nokia", "palo alto networks",
          "fortinet"]
_MID = ["crowdstrike", "zscaler", "okta", "datadog", "cloudflare", "snowflake",
        "mongodb", "hashicorp", "elastic", "gitlab", "twilio", "coinbase",
        "palantir", "databricks", "roblox", "pinterest", "dropbox", "doordash",
        "robinhood", "sentinelone", "tenable", "rapid7", "proofpoint", "sailpoint",
        "cyberark", "zoom", "docusign", "unity", "confluent", "netskope",
        "varonis", "dynatrace", "snap", "splunk", "spotify", "atlassian",
        "airbnb", "openai"]
_SMALL = ["wiz", "snyk", "semgrep", "sonarsource", "1password", "orca security",
          "aqua security", "sysdig", "lacework", "abnormal security", "vercel",
          "netlify", "retool", "temporal", "notion", "figma", "canva", "discord",
          "brex", "plaid", "rippling", "ramp", "airtable", "miro", "monzo",
          "affirm", "grafana", "anthropic"]
_STARTUP = ["mistral", "cohere", "perplexity", "hugging face", "scale ai",
            "anduril", "cockroach labs"]

# (bigness score 0-1, short band label). Bigger company -> higher score.
_SIZE_TIERS = [(1.00, "mega", _MEGA), (0.85, "large", _LARGE), (0.65, "mid", _MID),
               (0.45, "small", _SMALL), (0.30, "startup", _STARTUP)]
_SIZE_COMPILED = [(score, label, [_tokens(n) for n in names])
                  for score, label, names in _SIZE_TIERS]

# ordinal for "mid"-preference distance math (startup=0 ... mega=4)
SIZE_ORDER = {"startup": 0, "small": 1, "mid": 2, "large": 3, "mega": 4}


def company_size(company: str) -> tuple[float, str]:
    """Return (bigness 0-1, band label). Unknown companies get (0.5, "")."""
    ct = _tokens(company)
    if not ct:
        return 0.5, ""
    for score, label, namesets in _SIZE_COMPILED:
        for ns in namesets:
            if ns and ns <= ct:
                return score, label
    return 0.5, ""


# --- company funding tier (a compensation proxy) --------------------------
# Best-effort, curated. Funding correlates with ability/tendency to pay:
#   public  = publicly traded (liquid equity, generally strongest cash comp)
#   unicorn = private, ~$1B+ valuation / heavily VC-funded (strong comp + upside)
# Everything else is left blank (unknown). Funding drifts (IPOs, downrounds), so
# treat this as a rough band, not live Crunchbase data.
_PUBLIC = ["google", "alphabet", "meta", "apple", "amazon", "microsoft", "netflix",
           "nvidia", "oracle", "intel", "cisco", "sap", "adobe", "salesforce",
           "qualcomm", "broadcom", "paypal", "servicenow", "workday", "tesla", "uber",
           "lyft", "airbnb", "spotify", "atlassian", "block", "snap", "pinterest",
           "coinbase", "palantir", "datadog", "cloudflare", "snowflake", "mongodb",
           "gitlab", "twilio", "okta", "zscaler", "crowdstrike", "palo alto networks",
           "fortinet", "sentinelone", "tenable", "rapid7", "qualys", "varonis",
           "cyberark", "check point", "akamai", "elastic", "confluent", "hashicorp",
           "dynatrace", "docusign", "unity", "roblox", "dell", "hpe", "ibm", "amd",
           "micron", "visa", "mastercard", "adp", "intuit", "autodesk", "ebay",
           "cognizant", "infosys", "wipro", "tcs", "hcltech", "accenture", "capgemini"]
_UNICORN = ["stripe", "databricks", "canva", "openai", "anthropic", "wiz", "snyk",
            "netskope", "abnormal security", "orca security", "sysdig", "lacework",
            "rippling", "ramp", "notion", "figma", "discord", "airtable", "miro",
            "revolut", "plaid", "brex", "deel", "gusto", "vercel", "retool", "temporal",
            "grafana", "cockroach labs", "scale ai", "anduril", "mistral", "cohere",
            "perplexity", "hugging face", "1password", "tanium", "arctic wolf", "cyera",
            "island", "chainguard", "huntress", "semgrep", "socure", "aqua security"]

_FUNDING_TIERS = [("public", _PUBLIC), ("unicorn", _UNICORN)]
_FUNDING_COMPILED = [(label, [_tokens(n) for n in names]) for label, names in _FUNDING_TIERS]


def company_funding(company: str) -> str:
    """Return a funding tier ('public' | 'unicorn') or '' if unknown (comp proxy)."""
    ct = _tokens(company)
    if not ct:
        return ""
    for label, namesets in _FUNDING_COMPILED:
        for ns in namesets:
            if ns and ns <= ct:
                return label
    return ""
