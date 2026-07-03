"""Per-company enrichment sections and referral contacts."""
from __future__ import annotations

import json
from typing import Any, Iterable

from .base import now_iso


class EnrichmentMixin:
    # ---- enrichment -----------------------------------------------------
    def save_enrichment(self, company: str, **sections: Any) -> None:
        cols = {k: json.dumps(v) for k, v in sections.items()}
        existing = self.get_enrichment(company)
        merged = {**existing, **{k.replace("_json", ""): json.loads(v) for k, v in cols.items()}}
        self.conn.execute(
            """
            INSERT INTO enrichment (company, comp_json, stock_json, reddit_json,
                news_json, glassdoor_json, brief_json, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company) DO UPDATE SET
                comp_json=excluded.comp_json, stock_json=excluded.stock_json,
                reddit_json=excluded.reddit_json, news_json=excluded.news_json,
                glassdoor_json=excluded.glassdoor_json, brief_json=excluded.brief_json,
                updated=excluded.updated
            """,
            (
                company,
                json.dumps(merged.get("comp")),
                json.dumps(merged.get("stock")),
                json.dumps(merged.get("reddit")),
                json.dumps(merged.get("news")),
                json.dumps(merged.get("glassdoor")),
                json.dumps(merged.get("brief")),
                now_iso(),
            ),
        )
        self.conn.commit()

    def get_enrichment(self, company: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM enrichment WHERE company = ?", (company,)).fetchone()
        if not row:
            return {}
        out: dict[str, Any] = {}
        for section in ("comp", "stock", "reddit", "news", "glassdoor", "brief"):
            raw = row[f"{section}_json"]
            out[section] = json.loads(raw) if raw else None
        out["updated"] = row["updated"]
        return out

    # ---- contacts -------------------------------------------------------
    def save_contacts(self, contacts: Iterable[Any]) -> None:
        for c in contacts:
            self.conn.execute(
                """
                INSERT INTO contacts (id, company, name, title, source, profile_url,
                    search_url, outreach, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET outreach=excluded.outreach
                """,
                (c.id, c.company, c.name, c.title, c.source, c.profile_url,
                 c.search_url, c.outreach, now_iso()),
            )
        self.conn.commit()

    def contacts_for(self, company: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM contacts WHERE company = ?", (company,))
        return [dict(r) for r in rows]
