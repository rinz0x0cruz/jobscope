"""Stock / IPO enrichment via Yahoo Finance (yfinance + Yahoo search).

Resolves a company name to a ticker; when found the company is public and we
report price, day change, 52-week position, and market cap. No ticker => likely
private / pre-IPO. Keyless.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import httpx

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"

# common suffixes to strip when matching a company name to a listing
_NOISE = (" inc", " inc.", " llc", " ltd", " ltd.", " corp", " corp.", " corporation",
          " company", " co", " co.", " plc", " group", " holdings", " technologies",
          " technology", " labs", " ai", " software", " systems", ",", ".")


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
    payload = httpx.get_json(SEARCH_URL, params={"q": q, "quotesCount": 6, "newsCount": 0})
    if not payload:
        return None, None
    quotes = payload.get("quotes", []) or []
    target = _norm(company)
    best_score, best_symbol, best_name = 0, None, None
    for quote in quotes:
        if quote.get("quoteType") != "EQUITY" or not quote.get("symbol"):
            continue
        name = quote.get("shortname") or quote.get("longname") or ""
        score = _match_score(target, _norm(name), quote)
        if score > best_score:
            best_score, best_symbol, best_name = score, quote.get("symbol"), name
    if best_symbol:
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
