"""Application tracking: prepped/applied status joined back to jobs."""
from __future__ import annotations

from typing import Any, Optional

from .base import now_iso


class ApplicationsMixin:
    def set_application(self, app: Any) -> None:
        # Empty company/title/source never clobber existing values (an email sync
        # can enrich a prepped app, and a manual status change must not wipe a
        # previously parsed company); non-empty values overwrite.
        self.conn.execute(
            """
            INSERT INTO applications (job_id, status, package_dir, resume_path,
                cover_path, applied_at, notes, updated, company, title, source,
                outreach_at, outreach_to)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status, package_dir=excluded.package_dir,
                resume_path=excluded.resume_path, cover_path=excluded.cover_path,
                applied_at=excluded.applied_at, notes=excluded.notes, updated=excluded.updated,
                company=COALESCE(NULLIF(excluded.company, ''), applications.company),
                title=COALESCE(NULLIF(excluded.title, ''), applications.title),
                source=COALESCE(NULLIF(excluded.source, ''), applications.source),
                outreach_at=COALESCE(NULLIF(excluded.outreach_at, ''), applications.outreach_at),
                outreach_to=COALESCE(NULLIF(excluded.outreach_to, ''), applications.outreach_to)
            """,
            (app.job_id, app.status, app.package_dir, app.resume_path,
             app.cover_path, app.applied_at, app.notes, now_iso(),
             getattr(app, "company", ""), getattr(app, "title", ""),
             getattr(app, "source", ""), getattr(app, "outreach_at", ""),
             getattr(app, "outreach_to", "")),
        )
        self.conn.commit()

    def get_application(self, job_id_: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id_,)).fetchone()
        return dict(row) if row else None

    def append_note(self, job_id_: str, text: str) -> None:
        """Append a date-stamped note to an application (creating the row if needed),
        without disturbing its status or other fields."""
        stamped = f"[{now_iso()[:10]}] {text.strip()}"
        self.conn.execute(
            "INSERT INTO applications (job_id, status, notes, updated) "
            "VALUES (?, 'new', ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET "
            "notes = TRIM(COALESCE(applications.notes, '') || char(10) || excluded.notes), "
            "updated = excluded.updated",
            (job_id_, stamped, now_iso()))
        self.conn.commit()

    def mark_outreach(self, job_id_: str, to_addr: str, when: str = "") -> None:
        """Record a recruiter outreach for this job without disturbing its status."""
        ts = when or now_iso()
        self.conn.execute(
            "INSERT INTO applications (job_id, status, outreach_at, outreach_to, updated) "
            "VALUES (?, 'new', ?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET outreach_at=excluded.outreach_at, "
            "outreach_to=excluded.outreach_to, updated=excluded.updated",
            (job_id_, ts, to_addr, now_iso()))
        self.conn.commit()

    def last_company_outreach(self, company: str) -> Optional[str]:
        """Most recent outreach_at across this company's applications (or None)."""
        if not company:
            return None
        row = self.conn.execute(
            "SELECT MAX(a.outreach_at) AS last FROM applications a "
            "LEFT JOIN jobs j ON j.id = a.job_id "
            "WHERE COALESCE(NULLIF(j.company, ''), a.company) = ? "
            "AND a.outreach_at IS NOT NULL AND a.outreach_at <> ''",
            (company,)).fetchone()
        return row["last"] if row and row["last"] else None

    def applications(self) -> list[dict[str, Any]]:
        # Prefer the scraped job's company/title; fall back to the values parsed
        # from email for applications that have no matching job row.
        rows = self.conn.execute(
            "SELECT a.job_id, a.status, a.package_dir, a.resume_path, a.cover_path, "
            "a.applied_at, a.notes, a.updated, a.source, "
            "COALESCE(NULLIF(j.company, ''), a.company) AS company, "
            "COALESCE(NULLIF(j.title, ''), a.title) AS title, "
            "j.status AS job_status, j.closed_at "
            "FROM applications a "
            "LEFT JOIN jobs j ON j.id = a.job_id ORDER BY a.updated DESC"
        )
        return [dict(r) for r in rows]

    def purge_applications(self) -> int:
        """Delete every tracked application (empties the funnel). Returns the count
        removed. Stored emails are handled separately by ``purge_mail_events``."""
        cur = self.conn.execute("DELETE FROM applications")
        self.conn.commit()
        return cur.rowcount

    def delete_application(self, job_id_: str) -> int:
        """Delete a single application row (used when recompute rebuilds the
        instance rows for a company). Returns the number of rows removed."""
        cur = self.conn.execute("DELETE FROM applications WHERE job_id = ?", (job_id_,))
        self.conn.commit()
        return cur.rowcount
