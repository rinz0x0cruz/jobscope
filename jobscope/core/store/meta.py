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

    # ---- ai cache -------------------------------------------------------
    def ai_cache_get(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT response FROM ai_cache WHERE key = ?", (key,)).fetchone()
        return row["response"] if row else None

    def ai_cache_put(self, key: str, model: str, prompt: str, response: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_cache (key, model, prompt, response, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, model, prompt, response, now_iso()),
        )
        self.conn.commit()

    # ---- runs -----------------------------------------------------------
    def log_run(self, action: str, count: int, status: str) -> None:
        self.conn.execute(
            "INSERT INTO runs (ts, action, count, status) VALUES (?, ?, ?, ?)",
            (now_iso(), action, count, status),
        )
        self.conn.commit()
