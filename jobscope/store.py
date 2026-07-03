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
    remote_scope TEXT,
    raw_is_remote INTEGER,
    url TEXT,
    description TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_interval TEXT,
    currency TEXT,
    job_type TEXT,
    job_level TEXT,
    company_industry TEXT,
    company_url TEXT,
    date_posted TEXT,
    score REAL DEFAULT 0,
    tier TEXT,
    rationale TEXT,
    resume_base TEXT,
    ai_seniority TEXT,
    ai_required_years REAL,
    first_seen TEXT,
    last_seen TEXT,
    status TEXT DEFAULT 'open',
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS enrichment (
    company TEXT PRIMARY KEY,
    comp_json TEXT,
    stock_json TEXT,
    reddit_json TEXT,
    news_json TEXT,
    glassdoor_json TEXT,
    brief_json TEXT,
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
    updated TEXT,
    company TEXT,
    title TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    resume_json TEXT,
    resume_source TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS resumes (
    name TEXT PRIMARY KEY,
    resume_json TEXT,
    source TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
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
CREATE TABLE IF NOT EXISTS mail_events (
    id TEXT PRIMARY KEY,
    account TEXT,
    uid TEXT,
    message_id TEXT,
    thread_id TEXT,
    from_addr TEXT,
    from_name TEXT,
    from_domain TEXT,
    subject TEXT,
    date TEXT,
    company TEXT,
    role TEXT,
    signal TEXT,
    job_id TEXT,
    snippet TEXT,
    first_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_mail_events_job ON mail_events(job_id);
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
            ("resume_base", "TEXT"),
            ("status", "TEXT DEFAULT 'open'"),
            ("closed_at", "TEXT"),
            ("remote_scope", "TEXT"),
            ("raw_is_remote", "INTEGER"),
            ("job_level", "TEXT"),
            ("ai_seniority", "TEXT"),
            ("ai_required_years", "REAL"),
        ):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        enr = {r["name"] for r in self.conn.execute("PRAGMA table_info(enrichment)")}
        if "brief_json" not in enr:
            self.conn.execute("ALTER TABLE enrichment ADD COLUMN brief_json TEXT")
        appc = {r["name"] for r in self.conn.execute("PRAGMA table_info(applications)")}
        for col in ("company", "title", "source"):
            if col not in appc:
                self.conn.execute(f"ALTER TABLE applications ADD COLUMN {col} TEXT")
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

    # ---- applications ---------------------------------------------------
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

    # ---- mail events (inbound job-application emails) -------------------
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

    # ---- profile / resumes (supports multiple named base resumes) -------
    def save_resume(self, resume: Resume, name: str = "default") -> None:
        self.conn.execute(
            """
            INSERT INTO resumes (name, resume_json, source, updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                resume_json=excluded.resume_json, source=excluded.source, updated=excluded.updated
            """,
            (name, json.dumps(resume.to_dict()), resume.source_path, now_iso()),
        )
        self.conn.commit()

    def get_resume(self, name: Optional[str] = None) -> Optional[Resume]:
        """Return a named resume, or the primary (prefers 'default', else newest)."""
        if name:
            row = self.conn.execute(
                "SELECT resume_json FROM resumes WHERE name = ?", (name,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT resume_json FROM resumes ORDER BY (name = 'default') DESC, updated DESC "
                "LIMIT 1").fetchone()
        if not row or not row["resume_json"]:
            return None
        return Resume.from_dict(json.loads(row["resume_json"]))

    def get_named_resume(self, name: str) -> Optional[Resume]:
        return self.get_resume(name) if name else self.get_resume()

    def list_resumes(self) -> list[tuple[str, Resume]]:
        rows = self.conn.execute(
            "SELECT name, resume_json FROM resumes ORDER BY (name = 'default') DESC, name")
        out = []
        for r in rows:
            if r["resume_json"]:
                out.append((r["name"], Resume.from_dict(json.loads(r["resume_json"]))))
        return out

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


def _row_to_job(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["is_remote"] = bool(d.get("is_remote"))
    d["raw_is_remote"] = None if d.get("raw_is_remote") is None else bool(d.get("raw_is_remote"))
    return Job.from_dict(d)
