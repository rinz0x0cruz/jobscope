"""SQLite persistence for jobscope.

Follows the threatscope pattern: a single ``SCHEMA`` script, ``sqlite3.Row``
factory, an ``_ensure_columns`` migration hook for additive changes, and an
``now_iso`` helper. One database holds jobs, per-company enrichment, referral
contacts, application tracking, the profile/resume, and the AI response cache.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Iterable, Optional

from .model import Job, Resume

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    is_remote INTEGER DEFAULT 0,
    url TEXT,
    description TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_interval TEXT,
    currency TEXT,
    job_type TEXT,
    company_industry TEXT,
    company_url TEXT,
    date_posted TEXT,
    score REAL DEFAULT 0,
    tier TEXT,
    rationale TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS enrichment (
    company TEXT PRIMARY KEY,
    comp_json TEXT,
    stock_json TEXT,
    reddit_json TEXT,
    news_json TEXT,
    glassdoor_json TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    company TEXT,
    name TEXT,
    title TEXT,
    source TEXT,
    profile_url TEXT,
    search_url TEXT,
    outreach TEXT,
    first_seen TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    job_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'new',
    package_dir TEXT,
    resume_path TEXT,
    cover_path TEXT,
    applied_at TEXT,
    notes TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    resume_json TEXT,
    resume_source TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS ai_cache (
    key TEXT PRIMARY KEY,
    model TEXT,
    prompt TEXT,
    response TEXT,
    created TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    ts TEXT,
    action TEXT,
    count INTEGER,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Store:
    def __init__(self, path: str):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Additive migrations for older databases (mirrors threatscope)."""
        existing = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        for col, ddl in (
            ("company_industry", "TEXT"),
            ("company_url", "TEXT"),
        ):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- jobs -----------------------------------------------------------
    def upsert_job(self, job: Job) -> bool:
        """Insert or update a job. Returns True if newly inserted."""
        job.ensure_id()
        ts = now_iso()
        row = self.conn.execute("SELECT first_seen FROM jobs WHERE id = ?", (job.id,)).fetchone()
        is_new = row is None
        first_seen = row["first_seen"] if row and row["first_seen"] else ts
        self.conn.execute(
            """
            INSERT INTO jobs (id, source, title, company, location, is_remote, url,
                description, salary_min, salary_max, salary_interval, currency,
                job_type, company_industry, company_url, date_posted, score, tier,
                rationale, first_seen, last_seen)
            VALUES (:id, :source, :title, :company, :location, :is_remote, :url,
                :description, :salary_min, :salary_max, :salary_interval, :currency,
                :job_type, :company_industry, :company_url, :date_posted, :score, :tier,
                :rationale, :first_seen, :last_seen)
            ON CONFLICT(id) DO UPDATE SET
                source=excluded.source, title=excluded.title, company=excluded.company,
                location=excluded.location, is_remote=excluded.is_remote, url=excluded.url,
                description=excluded.description, salary_min=excluded.salary_min,
                salary_max=excluded.salary_max, salary_interval=excluded.salary_interval,
                currency=excluded.currency, job_type=excluded.job_type,
                company_industry=excluded.company_industry, company_url=excluded.company_url,
                date_posted=excluded.date_posted, last_seen=excluded.last_seen
            """,
            {
                **job.to_dict(),
                "is_remote": 1 if job.is_remote else 0,
                "first_seen": first_seen,
                "last_seen": ts,
            },
        )
        self.conn.commit()
        return is_new

    def update_score(self, job_id_: str, score: float, tier: str, rationale: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET score = ?, tier = ?, rationale = ? WHERE id = ?",
            (score, tier, rationale, job_id_),
        )
        self.conn.commit()

    def get_job(self, job_id_: str) -> Optional[Job]:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id_,)).fetchone()
        return _row_to_job(row) if row else None

    def jobs(self, order_by_score: bool = True, limit: Optional[int] = None) -> list[Job]:
        sql = "SELECT * FROM jobs"
        if order_by_score:
            sql += " ORDER BY score DESC, last_seen DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self.conn.execute(sql)]

    # ---- enrichment -----------------------------------------------------
    def save_enrichment(self, company: str, **sections: Any) -> None:
        cols = {k: json.dumps(v) for k, v in sections.items()}
        existing = self.get_enrichment(company)
        merged = {**existing, **{k.replace("_json", ""): json.loads(v) for k, v in cols.items()}}
        self.conn.execute(
            """
            INSERT INTO enrichment (company, comp_json, stock_json, reddit_json,
                news_json, glassdoor_json, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company) DO UPDATE SET
                comp_json=excluded.comp_json, stock_json=excluded.stock_json,
                reddit_json=excluded.reddit_json, news_json=excluded.news_json,
                glassdoor_json=excluded.glassdoor_json, updated=excluded.updated
            """,
            (
                company,
                json.dumps(merged.get("comp")),
                json.dumps(merged.get("stock")),
                json.dumps(merged.get("reddit")),
                json.dumps(merged.get("news")),
                json.dumps(merged.get("glassdoor")),
                now_iso(),
            ),
        )
        self.conn.commit()

    def get_enrichment(self, company: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM enrichment WHERE company = ?", (company,)).fetchone()
        if not row:
            return {}
        out: dict[str, Any] = {}
        for section in ("comp", "stock", "reddit", "news", "glassdoor"):
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

    # ---- applications ---------------------------------------------------
    def set_application(self, app: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO applications (job_id, status, package_dir, resume_path,
                cover_path, applied_at, notes, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status, package_dir=excluded.package_dir,
                resume_path=excluded.resume_path, cover_path=excluded.cover_path,
                applied_at=excluded.applied_at, notes=excluded.notes, updated=excluded.updated
            """,
            (app.job_id, app.status, app.package_dir, app.resume_path,
             app.cover_path, app.applied_at, app.notes, now_iso()),
        )
        self.conn.commit()

    def applications(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT a.*, j.title, j.company FROM applications a "
            "LEFT JOIN jobs j ON j.id = a.job_id ORDER BY a.updated DESC"
        )
        return [dict(r) for r in rows]

    # ---- profile / resume ----------------------------------------------
    def save_resume(self, resume: Resume) -> None:
        self.conn.execute(
            """
            INSERT INTO profile (id, resume_json, resume_source, updated)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                resume_json=excluded.resume_json, resume_source=excluded.resume_source,
                updated=excluded.updated
            """,
            (json.dumps(resume.to_dict()), resume.source_path, now_iso()),
        )
        self.conn.commit()

    def get_resume(self) -> Optional[Resume]:
        row = self.conn.execute("SELECT resume_json FROM profile WHERE id = 1").fetchone()
        if not row or not row["resume_json"]:
            return None
        return Resume.from_dict(json.loads(row["resume_json"]))

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


def _row_to_job(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["is_remote"] = bool(d.get("is_remote"))
    return Job.from_dict(d)
