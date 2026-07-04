"""Jobs table: upsert, scoring, AI seniority, reconciliation, and listing."""
from __future__ import annotations

from typing import Optional

from ..model import Job
from .base import _row_to_job, now_iso


class JobsMixin:
    def upsert_job(self, job: Job) -> bool:
        """Insert or update a job. Returns True if newly inserted."""
        job.ensure_id()
        ts = now_iso()
        row = self.conn.execute("SELECT first_seen FROM jobs WHERE id = ?", (job.id,)).fetchone()
        is_new = row is None
        first_seen = row["first_seen"] if row and row["first_seen"] else ts
        self.conn.execute(
            """
            INSERT INTO jobs (id, source, title, company, location, is_remote,
                remote_scope, raw_is_remote, url,
                description, salary_min, salary_max, salary_interval, currency,
                job_type, job_level, company_industry, company_url, date_posted, score, tier,
                rationale, first_seen, last_seen, status, closed_at)
            VALUES (:id, :source, :title, :company, :location, :is_remote,
                :remote_scope, :raw_is_remote, :url,
                :description, :salary_min, :salary_max, :salary_interval, :currency,
                :job_type, :job_level, :company_industry, :company_url, :date_posted, :score, :tier,
                :rationale, :first_seen, :last_seen, :status, :closed_at)
            ON CONFLICT(id) DO UPDATE SET
                source=excluded.source, title=excluded.title, company=excluded.company,
                location=excluded.location, is_remote=excluded.is_remote,
                remote_scope=excluded.remote_scope, raw_is_remote=excluded.raw_is_remote,
                url=excluded.url,
                description=excluded.description, salary_min=excluded.salary_min,
                salary_max=excluded.salary_max, salary_interval=excluded.salary_interval,
                currency=excluded.currency, job_type=excluded.job_type,
                job_level=excluded.job_level,
                company_industry=excluded.company_industry, company_url=excluded.company_url,
                date_posted=excluded.date_posted, last_seen=excluded.last_seen,
                status='open', closed_at=''
            """,
            {
                **job.to_dict(),
                "is_remote": 1 if job.is_remote else 0,
                "raw_is_remote": (None if job.raw_is_remote is None
                                  else (1 if job.raw_is_remote else 0)),
                "first_seen": first_seen,
                "last_seen": ts,
                "status": "open",
                "closed_at": "",
            },
        )
        self.conn.commit()
        return is_new

    def update_score(self, job_id_: str, score: float, tier: str, rationale: str,
                     resume_base: str = "") -> None:
        self.conn.execute(
            "UPDATE jobs SET score = ?, tier = ?, rationale = ?, resume_base = ? WHERE id = ?",
            (score, tier, rationale, resume_base, job_id_),
        )
        self.conn.commit()

    def update_ai_seniority(self, job_id_: str, level: str, years) -> None:
        """Persist an AI-classified seniority level + required years for a posting."""
        self.conn.execute(
            "UPDATE jobs SET ai_seniority = ?, ai_required_years = ? WHERE id = ?",
            (level, years, job_id_),
        )
        self.conn.commit()

    def get_job(self, job_id_: str) -> Optional[Job]:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id_,)).fetchone()
        return _row_to_job(row) if row else None

    def reconcile_open(self, source: str, company: str, live_urls) -> int:
        """Mark stored jobs from (source, company) that are no longer in the live
        URL set as closed (taken down). Returns how many were newly closed.

        Callers must only pass a *successfully fetched* board's URLs -- an empty
        set from a failed fetch would wrongly close everything.
        """
        live = {u for u in live_urls if u}
        if not live:
            return 0
        rows = self.conn.execute(
            "SELECT id, url FROM jobs WHERE source = ? AND company = ? "
            "AND (status IS NULL OR status = 'open')", (source, company)).fetchall()
        gone = [r["id"] for r in rows if (r["url"] or "") not in live]
        if gone:
            ts = now_iso()
            self.conn.executemany(
                "UPDATE jobs SET status = 'closed', closed_at = ? WHERE id = ?",
                [(ts, i) for i in gone])
            self.conn.commit()
        return len(gone)

    def closed_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'closed'").fetchone()[0]

    def jobs(self, order_by_score: bool = True, limit: Optional[int] = None) -> list[Job]:
        sql = "SELECT * FROM jobs"
        if order_by_score:
            sql += " ORDER BY score DESC, last_seen DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self.conn.execute(sql)]

    def delete_jobs(self, ids) -> int:
        """Hard-delete jobs by id. Returns the number of ids deleted."""
        ids = [i for i in ids if i]
        if not ids:
            return 0
        self.conn.executemany("DELETE FROM jobs WHERE id = ?", [(i,) for i in ids])
        self.conn.commit()
        return len(ids)
