"""Geographic scope: is a job applicable from your home country?

A role is *in scope* when you could realistically apply from where you live:

* it is located in your home country (onsite / hybrid), or
* it is remote with no country restriction (global), restricted to your home
  country, or restricted to a multi-country region that includes it (e.g. APAC /
  Asia for India).

Everything positively identified as *out of scope* -- onsite in another country,
or remote locked to a non-eligible country/region ("Remote - US", "Remote
(EMEA)") -- is dropped at ingest and by ``jobscope prune``. Jobs we cannot place
(empty / ambiguous location) are kept, never dropped on a guess.

Scope is config-driven: ``search.home_country`` (default "India") plus the
``search.scope_to_home`` toggle. India ships with the richest matching (state
codes + major metros); other home countries fall back to country-name matching,
so the same machinery works unchanged if you relocate.
"""
from __future__ import annotations

import re

from .model import Job

# Country code / alias -> canonical name (best-effort over messy location text).
_COUNTRY_CODES = {
    "in": "India", "ind": "India", "bharat": "India",
    "us": "United States", "usa": "United States", "u.s": "United States",
    "u.s.": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "gb": "United Kingdom", "gbr": "United Kingdom",
    "uae": "United Arab Emirates", "ae": "United Arab Emirates", "sg": "Singapore",
    "de": "Germany", "fr": "France", "il": "Israel", "my": "Malaysia", "it": "Italy",
    "ca": "Canada", "can": "Canada", "au": "Australia", "aus": "Australia",
    "nl": "Netherlands", "es": "Spain", "ie": "Ireland", "ch": "Switzerland",
    "se": "Sweden", "pl": "Poland", "jp": "Japan", "br": "Brazil", "mx": "Mexico",
    "ph": "Philippines", "id": "Indonesia", "pt": "Portugal",
}
# Recognized country names (lowercased). country_of() output that lands here and
# isn't the home country is a positive "foreign" signal -> dropped. An unrecognized
# token (a bare city like "Toronto", or garbage) is never dropped on a guess.
_KNOWN_COUNTRIES = {
    "india", "united states", "united kingdom", "canada", "australia", "germany",
    "france", "ireland", "netherlands", "spain", "italy", "sweden", "poland",
    "japan", "brazil", "mexico", "philippines", "indonesia", "portugal",
    "singapore", "israel", "malaysia", "united arab emirates", "switzerland",
    "china", "hong kong", "taiwan", "south korea", "korea", "vietnam", "thailand",
    "argentina", "chile", "colombia", "peru", "ecuador", "venezuela", "uruguay",
    "egypt", "nigeria", "kenya", "ghana", "south africa", "morocco", "tunisia",
    "ethiopia", "tanzania", "saudi arabia", "qatar", "kuwait", "bahrain", "oman",
    "jordan", "lebanon", "turkey", "greece", "austria", "belgium", "norway",
    "finland", "denmark", "iceland", "czechia", "czech republic", "romania",
    "hungary", "ukraine", "russia", "belarus", "new zealand", "luxembourg",
    "estonia", "lithuania", "latvia", "slovakia", "slovenia", "croatia", "serbia",
    "bosnia", "bulgaria", "cyprus", "malta", "bangladesh", "pakistan", "sri lanka",
    "nepal", "bhutan", "myanmar", "cambodia", "laos", "mongolia", "kazakhstan",
    "uzbekistan", "azerbaijan", "armenia", "georgia", "albania", "macedonia",
    "moldova", "montenegro", "kosovo", "panama", "costa rica", "guatemala",
    "honduras", "el salvador", "nicaragua", "dominican republic", "bolivia",
    "paraguay", "iraq", "iran", "syria", "yemen", "afghanistan", "algeria",
    "angola", "zimbabwe", "zambia", "uganda", "senegal", "mauritius", "fiji",
}

# Indian state / UT codes (Indeed-style "…, MH, IN") -> state name.
_IN_STATES = {
    "mh": "Maharashtra", "ka": "Karnataka", "ts": "Telangana", "tn": "Tamil Nadu",
    "dl": "Delhi", "hr": "Haryana", "up": "Uttar Pradesh", "gj": "Gujarat",
    "wb": "West Bengal", "rj": "Rajasthan", "pb": "Punjab", "kl": "Kerala",
    "ap": "Andhra Pradesh", "mp": "Madhya Pradesh", "ga": "Goa", "od": "Odisha",
}
# Major Indian metros (substring match on the location string).
_IN_CITIES = {
    "bengaluru", "bangalore", "mumbai", "new delhi", "delhi", "gurugram", "gurgaon",
    "noida", "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "jaipur",
    "kochi", "cochin", "coimbatore", "indore", "chandigarh", "trivandrum",
    "thiruvananthapuram", "nagpur", "vadodara", "visakhapatnam", "mysuru", "mysore",
    "bhubaneswar", "ncr",
}
# Indian state codes that are NOT also US state codes -- safe as a standalone
# "this is India" signal. TN (Tennessee) and GA (Georgia) overlap US states, so
# they need a city / "India" marker instead and are excluded here.
_IN_ONLY_CODES = set(_IN_STATES) - {"tn", "ga"}
# US state / DC codes -> treated as United States, so US-onsite "City, ST" drops.
# Codes already meaning a foreign country (ca/de/id) or India (in) are excluded so
# their existing mapping wins.
_US_STATES = {
    "al", "ak", "az", "ar", "co", "ct", "fl", "ga", "hi", "ia", "il", "ks", "ky",
    "la", "ma", "md", "me", "mi", "mn", "mo", "ms", "mt", "nc", "nd", "ne", "nh",
    "nj", "nm", "nv", "ny", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx",
    "ut", "va", "vt", "wa", "wi", "wv", "wy", "dc",
}
# Full Indian state / UT names (substring match) -- a positive India signal that
# catches onsite roles named by state ("Kanpur, Uttar Pradesh"). Punjab / Kashmir
# are omitted (shared with Pakistan); their cities cover the Indian side.
_IN_REGIONS = {
    "andhra pradesh", "arunachal", "assam", "bihar", "chhattisgarh", "goa",
    "gujarat", "haryana", "himachal", "jharkhand", "karnataka", "kerala",
    "madhya pradesh", "maharashtra", "manipur", "meghalaya", "nagaland",
    "odisha", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal", "puducherry",
}
# Work-mode words that are not places (peeled off when isolating a country token).
_WORKMODE = ("remote", "onsite", "on-site", "hybrid", "anywhere", "flexible", "wfh")
# Remote-scope regions that INCLUDE India (an India resident may apply).
_INDIA_REMOTE_OK = {
    "", "global", "worldwide", "anywhere", "india",
    "apac", "asia", "asia pacific", "asia-pacific", "south asia",
}


def country_of(job: Job) -> str:
    """Best-effort country from a messy location string ('' if unknown/city-only)."""
    loc = (job.location or "").strip()
    if not loc:
        return ""
    cleaned = re.sub(r"\([^)]*\)", " ", loc)                 # drop "(Remote)" etc.
    for seg in reversed([s for s in re.split(r"[,;/]", cleaned) if s.strip()]):
        words = [w for w in seg.split()
                 if w.strip(".-") and w.lower().strip(".-") not in _WORKMODE]
        cand = re.sub(r"-?(?:remote|wfh)$", "", " ".join(words), flags=re.I).strip(" .-")
        if cand:
            cl = cand.lower()
            if cl in _US_STATES:
                return "United States"
            return _COUNTRY_CODES.get(cl, cand)
    return ""


def _looks_indian(loc: str) -> bool:
    """True if the location text names India, an Indian state code, or a metro."""
    low = (loc or "").lower()
    if not low:
        return False
    if re.search(r"\bindia\b", low) or any(c in low for c in _IN_CITIES) \
            or any(r in low for r in _IN_REGIONS):
        return True
    segs = [s.strip().strip(".") for s in low.split(",") if s.strip()]
    if segs and segs[-1] in ("in", "india"):
        return True
    return any(s in _IN_ONLY_CODES for s in segs)


def is_home_location(job: Job, home: str = "India") -> bool:
    """True if the job is physically located in the home country."""
    loc = (job.location or "").strip()
    if not loc:
        return False
    home_l = (home or "India").strip().lower()
    if home_l == "india" and _looks_indian(loc):
        return True
    ctry = country_of(job)
    return bool(ctry) and ctry.strip().lower() == home_l


def _remote_ok(job: Job, home_l: str) -> bool:
    """Whether a remote job's country restriction (if any) permits the home country."""
    scope = (job.remote_scope or "").strip().lower()
    allowed = _INDIA_REMOTE_OK if home_l == "india" else {"", "global", "worldwide", "anywhere", home_l}
    if scope and scope not in allowed:
        return False                                          # explicit non-eligible region
    # A "global"-looking scope can still hide a country in the location text
    # ("United States (Remote)" parses to global); reject a recognized foreign country.
    if home_l == "india" and _looks_indian(job.location or ""):
        return True
    ctry = country_of(job).strip().lower()
    if ctry in _KNOWN_COUNTRIES and ctry != home_l:
        return False
    return True


def in_scope(job: Job, home: str = "India") -> bool:
    """Whether a role is applicable from ``home`` (home-country onsite, or eligible remote).

    Ambiguous / unknown locations are kept (returns True); only a *positive*
    out-of-country signal drops a job.
    """
    home_l = (home or "India").strip().lower()
    if job.is_remote:
        return _remote_ok(job, home_l)
    if is_home_location(job, home):
        return True
    # onsite, non-home: drop only when we positively recognize a foreign country.
    ctry = country_of(job).strip().lower()
    if ctry in _KNOWN_COUNTRIES and ctry != home_l:
        return False
    return True
