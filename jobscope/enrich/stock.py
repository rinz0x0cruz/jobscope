"""Stock / IPO enrichment via Yahoo Finance (yfinance + Yahoo search).

Resolves a company name to a ticker; when found the company is public and we
report price, day change, 52-week position, and market cap. No ticker => likely
private / pre-IPO. Keyless.
"""
from __future__ import annotations

from typing import Any, Optional

from jobscope.core import httpx
from .registry import source

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"

# common suffixes to strip when matching a company name to a listing
_NOISE = (" inc", " inc.", " llc", " ltd", " ltd.", " corp", " corp.", " corporation",
          " company", " co", " co.", " plc", " group", " holdings", " technologies",
          " technology", " labs", " ai", " software", " systems", ",", ".")

# Yahoo `exchange` codes for primary US listings; anything else (a foreign or
# secondary listing) is rejected so a company name can't be matched to an unrelated
# overseas ticker (e.g. "wiz" -> a Korean "038620.KQ").
_US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "BATS", "NAS", "NYS", "NIM"}

# Curated overrides for the employers jobscope tracks: a US ticker when public, or
# None when known-private / pre-IPO (so we never guess a wrong listing). Looked up by
# _norm(company), so both the ATS board name ("wiz") and scraped forms ("Wiz, Inc.")
# resolve here. Anything not listed falls through to the (hardened) Yahoo search.
KNOWN_TICKERS: dict[str, Optional[str]] = {
    "datadog": "DDOG", "snowflake": "SNOW", "okta": "OKTA", "zscaler": "ZS",
    "cloudflare": "NET", "mongodb": "MDB", "gitlab": "GTLB", "confluent": "CFLT",
    "coinbase": "COIN", "dropbox": "DBX", "elastic": "ESTC", "rubrik": "RBRK",
    "samsara": "IOT", "robinhood": "HOOD", "crowdstrike": "CRWD",
    "palo alto networks": "PANW", "sentinelone": "S", "inseego": "INSG",
    "wiz": None, "anduril": None, "ramp": None, "notion": None, "openai": None,
    "chainguard": None, "vanta": None, "abnormal": None, "abnormal security": None,
    "huntress": None, "semgrep": None, "tines": None, "material": None,
    "material security": None, "orca": None, "orca security": None, "drata": None,
    "temporal": None, "render": None, "databricks": None, "stripe": None,
    "discord": None, "brex": None, "gusto": None, "postman": None, "sysdig": None,
    "cockroachlabs": None, "cockroach": None, "mistral": None, "clickhouse": None,
    "fivetran": None, "grafanalabs": None, "grafana": None, "vercel": None,
}


@source(section="stock", config_key="stock")
def enrich(company: str) -> Optional[dict[str, Any]]:
    ticker, longname = _resolve_ticker(company)
    if not ticker:
        return {"public": False, "note": "no public equity found (private / pre-IPO?)"}

    data: dict[str, Any] = {"public": True, "ticker": ticker, "name": longname or company}
    try:
        import yfinance as yf
    except ImportError:
        data["note"] = "install yfinance for price data"
        return data

    try:
        fi = yf.Ticker(ticker).fast_info
        price = _f(getattr(fi, "last_price", None))
        prev = _f(getattr(fi, "previous_close", None))
        hi = _f(getattr(fi, "year_high", None))
        lo = _f(getattr(fi, "year_low", None))
        cap = _f(getattr(fi, "market_cap", None))
        cur = getattr(fi, "currency", None) or "USD"
        if price is not None:
            data["price"] = round(price, 2)
            data["currency"] = cur
        if price is not None and prev:
            data["change_pct"] = round((price - prev) / prev * 100, 2)
        if hi and lo and price is not None and hi > lo:
            data["week52_low"] = round(lo, 2)
            data["week52_high"] = round(hi, 2)
            data["week52_pos_pct"] = round((price - lo) / (hi - lo) * 100, 1)
        if cap:
            data["market_cap"] = _human(cap)
            data["market_cap_raw"] = cap
    except Exception as e:  # noqa: BLE001 - best-effort
        data["note"] = f"price lookup failed: {e}"
    return data


def _resolve_ticker(company: str) -> tuple[Optional[str], Optional[str]]:
    q = (company or "").strip()
    if not q:
        return None, None
    key = _norm(company)
    if key in KNOWN_TICKERS:                       # curated override wins (deterministic)
        ticker = KNOWN_TICKERS[key]
        return (ticker, None) if ticker else (None, None)   # None => known private
    payload = httpx.get_json(SEARCH_URL, params={"q": q, "quotesCount": 6, "newsCount": 0})
    if not payload:
        return None, None
    quotes = payload.get("quotes", []) or []
    target = _norm(company)
    best_score, best_symbol, best_name = 0, None, None
    for quote in quotes:
        if quote.get("quoteType") != "EQUITY" or not quote.get("symbol"):
            continue
        # Only trust a *primary US* listing; a foreign/secondary hit (e.g. a Korean
        # ".KQ" whose short name also reduces to the query) is almost always wrong.
        if quote.get("exchange") not in _US_EXCHANGES:
            continue
        name = quote.get("shortname") or quote.get("longname") or ""
        score = _match_score(target, _norm(name), quote)
        if score > best_score:
            best_score, best_symbol, best_name = score, quote.get("symbol"), name
    # Require real confidence: an exact or containment name match (>=60), not a mere
    # shared first word. Otherwise treat the company as private/unknown (fail safe).
    if best_symbol and best_score >= 60:
        return best_symbol, best_name
    return None, None


def _match_score(target: str, name: str, quote: dict) -> int:
    score = 0
    if not name:
        return 0
    if target == name:
        score += 100
    elif target and (target in name or name in target):
        score += 60
    elif target and target.split()[0] == (name.split() or [""])[0]:
        score += 30
    # prefer major US exchanges
    if quote.get("exchange") in ("NMS", "NYQ", "NGM", "NCM"):
        score += 5
    return score


def _norm(s: str) -> str:
    s = (s or "").lower()
    for n in _NOISE:
        s = s.replace(n, " ")
    return " ".join(s.split())


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _human(n: float) -> str:
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"${n / div:.1f}{unit}"
    return f"${n:.0f}"
