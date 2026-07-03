"""Inbound job-application email events (classified, idempotent)."""
from __future__ import annotations

import time
from typing import Any, Optional

from .base import now_iso


class MailMixin:
    def upsert_mail_event(self, ev: Any) -> bool:
        """Insert a classified email event. Returns True if newly inserted;
        idempotent -- re-processing the same message is a no-op."""
        ev.ensure_id()
        row = self.conn.execute(
            "SELECT id FROM mail_events WHERE id = ?", (ev.id,)).fetchone()
        if row is not None:
            return False
        self.conn.execute(
            """
            INSERT INTO mail_events (id, account, uid, message_id, thread_id,
                from_addr, from_name, from_domain, subject, date, company, role,
                signal, job_id, snippet, first_seen)
            VALUES (:id, :account, :uid, :message_id, :thread_id, :from_addr,
                :from_name, :from_domain, :subject, :date, :company, :role,
                :signal, :job_id, :snippet, :first_seen)
            """,
            {**ev.to_dict(), "first_seen": ev.first_seen or now_iso()},
        )
        self.conn.commit()
        return True

    def mail_events(self, job_id_: Optional[str] = None) -> list[dict[str, Any]]:
        if job_id_:
            rows = self.conn.execute(
                "SELECT * FROM mail_events WHERE job_id = ? ORDER BY date, first_seen",
                (job_id_,))
        else:
            rows = self.conn.execute("SELECT * FROM mail_events ORDER BY date, first_seen")
        return [dict(r) for r in rows]

    def purge_mail_events(self, older_than_days: Optional[int] = None) -> int:
        """Delete stored email events -- the recruiter PII and body snippets. With
        ``older_than_days`` set, only events older than that cutoff are removed
        (retention); otherwise all of them. Returns the number of rows deleted."""
        if older_than_days is not None:
            cutoff = time.strftime(
                "%Y-%m-%d", time.gmtime(time.time() - older_than_days * 86400))
            cur = self.conn.execute(
                "DELETE FROM mail_events WHERE substr(date, 1, 10) < ?", (cutoff,))
        else:
            cur = self.conn.execute("DELETE FROM mail_events")
        self.conn.commit()
        return cur.rowcount
