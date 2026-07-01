"""Company news enrichment via Google News RSS (keyless).

Uses feedparser (same approach as threatscope's RSS ingest). Optional extra feed
URLs from config are scanned and filtered to entries that mention the company.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def enrich(company: str, extra_feeds: list[str] | None = None) -> Optional[list[dict[str, Any]]]:
    try:
        import feedparser
    except ImportError:
        return None

    items: list[dict[str, Any]] = []
    url = GOOGLE_NEWS.format(q=quote_plus(f'"{company}"'))
    try:
        feed = feedparser.parse(url)
        for e in feed.entries[:8]:
            items.append({
                "title": getattr(e, "title", "")[:180],
                "link": getattr(e, "link", ""),
                "published": getattr(e, "published", ""),
                "source": (getattr(e, "source", {}) or {}).get("title", "")
                if hasattr(e, "source") else "",
            })
    except Exception:  # noqa: BLE001 - best-effort
        pass

    for furl in (extra_feeds or []):
        try:
            feed = feedparser.parse(furl)
            low = company.lower()
            for e in feed.entries:
                title = getattr(e, "title", "")
                summary = getattr(e, "summary", "")
                if low in (title + " " + summary).lower():
                    items.append({"title": title[:180], "link": getattr(e, "link", ""),
                                  "published": getattr(e, "published", ""), "source": furl})
        except Exception:  # noqa: BLE001
            continue

    # de-dup by title, keep order
    seen, out = set(), []
    for it in items:
        key = it["title"].lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out[:8] or None
