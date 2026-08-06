"""Manual next actions: the few steps that cannot be derived from other state."""
from __future__ import annotations

import hashlib

from .base import now_iso

STATES = ("open", "completed", "cancelled")


class ManualActionsMixin:
    def add_manual_action(self, label: str, *, due_at: str = "", job_id: str = "",
                          company: str = "", note: str = "") -> dict:
        """Record one step the user decided on. Returns the stored row."""
        text = (label or "").strip()
        if not text:
            raise ValueError("a manual action needs a label")
        created = now_iso()
        # Same label, job and due date entered twice is the same intent, so the id is
        # derived from them: re-adding updates rather than stacking duplicates.
        seed = f"{job_id}|{text.lower()}|{due_at}".encode()
        action_id = f"act:{hashlib.sha256(seed).hexdigest()[:16]}"
        self.conn.execute(
            "INSERT INTO manual_actions "
            "(id, job_id, company, label, due_at, state, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, '') "
            "ON CONFLICT(id) DO UPDATE SET company = excluded.company, "
            "note = excluded.note, updated_at = excluded.created_at",
            (action_id, job_id or "", company or "", text, due_at or "", note or "", created),
        )
        self.conn.commit()
        return self.manual_action(action_id) or {}

    def manual_action(self, action_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM manual_actions WHERE id = ?", (action_id,)).fetchone()
        return dict(row) if row else None

    def manual_actions(self, *, state: str = "") -> list[dict]:
        """Stored actions, soonest due first. Undated ones sort last."""
        sql = "SELECT * FROM manual_actions"
        params: tuple = ()
        if state:
            sql += " WHERE state = ?"
            params = (state,)
        sql += " ORDER BY CASE WHEN due_at = '' THEN 1 ELSE 0 END, due_at, created_at"
        return [dict(row) for row in self.conn.execute(sql, params)]

    def set_manual_action_state(self, action_id: str, state: str) -> bool:
        """Move one action between open, completed and cancelled.

        Every transition is allowed in both directions: a step marked done by mistake
        has to be recoverable, and nothing here asserts an application status or an
        email outcome, so reopening invents nothing.
        """
        if state not in STATES:
            raise ValueError(f"unknown action state: {state}")
        cursor = self.conn.execute(
            "UPDATE manual_actions SET state = ?, updated_at = ? WHERE id = ?",
            (state, now_iso(), action_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0
