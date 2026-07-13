"""Application tracking: prepped/applied status joined back to jobs."""
from __future__ import annotations

import json
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
                outreach_at, outreach_to, interview_at, salary_offered, offer_accepted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status, package_dir=excluded.package_dir,
                resume_path=excluded.resume_path, cover_path=excluded.cover_path,
                applied_at=excluded.applied_at, notes=excluded.notes, updated=excluded.updated,
                company=COALESCE(NULLIF(excluded.company, ''), applications.company),
                title=COALESCE(NULLIF(excluded.title, ''), applications.title),
                source=COALESCE(NULLIF(excluded.source, ''), applications.source),
                outreach_at=COALESCE(NULLIF(excluded.outreach_at, ''), applications.outreach_at),
                outreach_to=COALESCE(NULLIF(excluded.outreach_to, ''), applications.outreach_to),
                interview_at=COALESCE(NULLIF(excluded.interview_at, ''), applications.interview_at),
                salary_offered=COALESCE(NULLIF(excluded.salary_offered, ''), applications.salary_offered),
                offer_accepted=COALESCE(NULLIF(excluded.offer_accepted, ''), applications.offer_accepted)
            """,
            (app.job_id, app.status, app.package_dir, app.resume_path,
             app.cover_path, app.applied_at, app.notes, now_iso(),
             getattr(app, "company", ""), getattr(app, "title", ""),
             getattr(app, "source", ""), getattr(app, "outreach_at", ""),
             getattr(app, "outreach_to", ""), getattr(app, "interview_at", ""),
             getattr(app, "salary_offered", ""), getattr(app, "offer_accepted", "")),
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

    def set_offer(self, job_id_: str, *, interview_at: str = "", salary_offered: str = "",
                  offer_accepted: str = "") -> None:
        """Upsert offer/interview fields on an application without touching its status.

        Empty values never clobber existing ones (same guard as ``set_application``),
        so a partial update from the dashboard only writes the fields it changed."""
        self.conn.execute(
            "INSERT INTO applications (job_id, status, interview_at, salary_offered, "
            "offer_accepted, updated) VALUES (?, 'new', ?, ?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET "
            "interview_at=COALESCE(NULLIF(excluded.interview_at, ''), applications.interview_at), "
            "salary_offered=COALESCE(NULLIF(excluded.salary_offered, ''), applications.salary_offered), "
            "offer_accepted=COALESCE(NULLIF(excluded.offer_accepted, ''), applications.offer_accepted), "
            "updated=excluded.updated",
            (job_id_, interview_at, salary_offered, offer_accepted, now_iso()))
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
            "a.interview_at, a.salary_offered, a.offer_accepted, "
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

    # -- applied-company HR contacts (outreach pre-compute) -------------------
    def active_application_companies(self, limit: int = 25) -> list[dict[str, Any]]:
        """Distinct companies with an in-flight application (applied/interview -- not
        rejected/offer, and not on a closed job), most-recently active first. One
        row per company, capped at ``limit`` -- the set worth cold-contacting HR at.

        Uses SQLite's ``GROUP BY``/``MAX`` bare-column form: the row with the latest
        ``updated`` per company supplies the status/applied_at/company_url."""
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(j.company, ''), a.company) AS company, a.status, "
            "       a.applied_at, MAX(a.updated) AS updated, j.company_url AS company_url "
            "FROM applications a LEFT JOIN jobs j ON j.id = a.job_id "
            "WHERE a.status IN ('applied', 'interview') "
            "  AND COALESCE(j.status, 'open') <> 'closed' "
            "  AND COALESCE(NULLIF(j.company, ''), a.company) <> '' "
            "GROUP BY COALESCE(NULLIF(j.company, ''), a.company) "
            "ORDER BY COALESCE(NULLIF(applied_at, ''), updated) DESC, company "
            "LIMIT ?",
            (limit,))
        return [dict(r) for r in rows]

    def set_company_contacts(self, company: str, domain: str, contacts: list[dict]) -> None:
        """Persist discovered HR contacts for a company (upsert, keyed by company)."""
        self.conn.execute(
            "INSERT INTO company_contacts (company, domain, contacts_json, discovered_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(company) DO UPDATE SET "
            "domain = excluded.domain, contacts_json = excluded.contacts_json, "
            "discovered_at = excluded.discovered_at",
            (company, domain, json.dumps(contacts or []), now_iso()))
        self.conn.commit()

    def get_company_contacts(self, company: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT company, domain, contacts_json, discovered_at FROM company_contacts "
            "WHERE company = ?", (company,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["contacts"] = json.loads(d.pop("contacts_json") or "[]")
        return d

    def list_company_contacts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT company, domain, contacts_json, discovered_at FROM company_contacts")
        out = []
        for r in rows:
            d = dict(r)
            d["contacts"] = json.loads(d.pop("contacts_json") or "[]")
            out.append(d)
        return out
