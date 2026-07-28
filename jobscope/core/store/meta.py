"""Key/value markers, the AI response cache, and the run log."""
from __future__ import annotations

from typing import Optional

from .base import now_iso


class MetaMixin:
    # ---- meta (key/value markers, e.g. last_review) ---------------------
    def meta_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def meta_compare_and_set(
        self, key: str, expected: Optional[str], value: Optional[str],
    ) -> bool:
        """Atomically insert, replace, or delete one exact metadata value."""
        if self.conn.in_transaction:
            self.conn.commit()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if expected is None:
                if value is None:
                    self.conn.rollback()
                    return False
                cursor = self.conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO NOTHING",
                    (key, value),
                )
            elif value is None:
                cursor = self.conn.execute(
                    "DELETE FROM meta WHERE key = ? AND value = ?",
                    (key, expected),
                )
            else:
                cursor = self.conn.execute(
                    "UPDATE meta SET value = ? WHERE key = ? AND value = ?",
                    (value, key, expected),
                )
            self.conn.commit()
            return cursor.rowcount == 1
        except Exception:
            self.conn.rollback()
            raise

    def meta_finalize_intent(
        self, intent_key: str, expected_intent: str,
        marker_key: str, marker_value: str,
    ) -> bool:
        """Atomically promote a marker and remove its exact completed intent."""
        if self.conn.in_transaction:
            self.conn.commit()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.conn.execute(
                "DELETE FROM meta WHERE key = ? AND value = ?",
                (intent_key, expected_intent),
            )
            if cursor.rowcount != 1:
                self.conn.rollback()
                return False
            self.conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (marker_key, marker_value),
            )
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    # ---- ai cache -------------------------------------------------------
    def ai_cache_get(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT response FROM ai_cache WHERE key = ?", (key,)).fetchone()
        return row["response"] if row else None

    def ai_cache_put(self, key: str, model: str, prompt: str, response: str) -> None:
        # The cache key already hashes model + system + user. Persisting the raw
        # prompt adds unneeded scraped text and candidate context at rest.
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_cache (key, model, prompt, response, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, model, "", response, now_iso()),
        )
        self.conn.commit()

    # ---- runs -----------------------------------------------------------
    def log_run(self, action: str, count: int, status: str) -> None:
        self.conn.execute(
            "INSERT INTO runs (ts, action, count, status) VALUES (?, ?, ?, ?)",
            (now_iso(), action, count, status),
        )
        self.conn.commit()

    def set_source_health(self, source: str, *, provider: str, slug: str,
                          status: str, item_count: int = 0, attempts: int = 0,
                          status_code: int | None = None, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO source_health "
            "(source, provider, slug, status, item_count, attempts, status_code, detail, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET "
            "provider=excluded.provider, slug=excluded.slug, status=excluded.status, "
            "item_count=excluded.item_count, attempts=excluded.attempts, "
            "status_code=excluded.status_code, detail=excluded.detail, "
            "checked_at=excluded.checked_at",
            (source, provider, slug, status, item_count, attempts, status_code,
             (detail or "")[:500], now_iso()),
        )
        self.conn.commit()

    def source_health(self, source: str | None = None) -> list[dict]:
        if source is None:
            rows = self.conn.execute(
                "SELECT * FROM source_health ORDER BY source"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM source_health WHERE source = ?", (source,)
            ).fetchall()
        return [dict(row) for row in rows]
