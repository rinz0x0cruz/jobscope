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
                cover_path, applied_at, notes, updated, company, title, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status, package_dir=excluded.package_dir,
                resume_path=excluded.resume_path, cover_path=excluded.cover_path,
                applied_at=excluded.applied_at, notes=excluded.notes, updated=excluded.updated,
                company=COALESCE(NULLIF(excluded.company, ''), applications.company),
                title=COALESCE(NULLIF(excluded.title, ''), applications.title),
                source=COALESCE(NULLIF(excluded.source, ''), applications.source)
            """,
            (app.job_id, app.status, app.package_dir, app.resume_path,
             app.cover_path, app.applied_at, app.notes, now_iso(),
             getattr(app, "company", ""), getattr(app, "title", ""),
             getattr(app, "source", "")),
        )
        self.conn.commit()

    def get_application(self, job_id_: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id_,)).fetchone()
        return dict(row) if row else None

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
