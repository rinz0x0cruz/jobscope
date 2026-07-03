"""Reddit sentiment enrichment via the public search JSON (keyless, best-effort).

Deterministic lexicon sentiment over post titles now; `tailor`/`ai` can layer a
nuanced summary later. Always returns a `search_url` so the user can dig in.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus

from .. import httpx
from .registry import source

SEARCH_URL = "https://www.reddit.com/search.json"

POS = {"great", "love", "good", "best", "amazing", "excellent", "positive", "happy",
       "recommend", "smart", "growth", "wlb", "work-life", "flexible", "generous",
       "friendly", "supportive", "impressive", "strong", "fair", "respect"}
NEG = {"bad", "worst", "toxic", "layoff", "layoffs", "fired", "avoid", "scam", "poor",
       "terrible", "awful", "stress", "stressful", "burnout", "micromanage", "underpaid",
       "overworked", "rejected", "ghosted", "shady", "nightmare", "quit", "pip"}


@source(section="reddit", config_key="reddit")
def enrich(company: str) -> Optional[dict[str, Any]]:
    q = f'"{company}"'
    payload = httpx.get_json(
        SEARCH_URL,
        params={"q": q, "sort": "relevance", "t": "year", "limit": 12},
    )
    search_url = f"https://www.reddit.com/search/?q={quote_plus(q)}&t=year"
    if not payload:
        return {"count": 0, "sentiment": "unknown", "search_url": search_url}

    children = (payload.get("data", {}) or {}).get("children", []) or []
    posts = []
    pos = neg = 0
    for ch in children:
        d = ch.get("data", {})
        title = d.get("title", "")
        if not title:
            continue
        toks = set(w.strip(".,!?()[]'\"").lower() for w in title.split())
        pos += len(toks & POS)
        neg += len(toks & NEG)
        posts.append({
            "title": title[:160],
            "subreddit": d.get("subreddit_name_prefixed", d.get("subreddit", "")),
            "score": d.get("score", 0),
            "comments": d.get("num_comments", 0),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
        })

    posts.sort(key=lambda p: p.get("score", 0), reverse=True)
    return {
        "count": len(posts),
        "sentiment": _label(pos, neg),
        "summary": "; ".join(p["title"] for p in posts[:3]),
        "posts": posts[:8],
        "search_url": search_url,
    }


def _label(pos: int, neg: int) -> str:
    if pos == 0 and neg == 0:
        return "neutral"
    if pos >= neg * 2:
        return "positive"
    if neg >= pos * 2:
        return "negative"
    return "mixed"
