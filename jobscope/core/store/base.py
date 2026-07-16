"""Connection setup, schema, migrations, and shared helpers for the store package.

This module holds the single-connection base class every domain mixin composes
over, the ``SCHEMA`` DDL, the additive ``_ensure_columns`` migration, and the
``now_iso`` / ``_row_to_job`` helpers. The concern mixins (``jobs``,
``enrichment``, ``applications``, ``mail``, ``profile``, ``meta``) all operate on
the same ``self`` / connection established here; the package ``__init__``
assembles them into the public ``Store`` facade.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

from ..model import Job

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
CREATE TABLE IF NOT EXISTS job_analysis (
    job_id TEXT NOT NULL,
    resume_base TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL,
    comp_json TEXT,
    brief_json TEXT,
    updated TEXT,
    PRIMARY KEY (job_id, resume_base, version)
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
    source TEXT,
    outreach_at TEXT,
    outreach_to TEXT,
    interview_at TEXT,
    salary_offered TEXT,
    offer_accepted TEXT,
    tombstoned_at TEXT,
    tombstone_reason TEXT,
    reconciliation_run_id TEXT,
    reconciliation_exempt INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reconciliation_runs (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK (action IN ('recompute', 'reclassify', 'restore')),
    initiator TEXT NOT NULL CHECK (initiator IN ('cli', 'local_refresh', 'cloud_refresh', 'user')),
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    applications_before INTEGER NOT NULL DEFAULT 0,
    applications_after INTEGER,
    events_before INTEGER NOT NULL DEFAULT 0,
    events_after INTEGER,
    groups_count INTEGER NOT NULL DEFAULT 0,
    instances_count INTEGER NOT NULL DEFAULT 0,
    reclassified_count INTEGER NOT NULL DEFAULT 0,
    dropped_count INTEGER NOT NULL DEFAULT 0,
    tombstoned_count INTEGER NOT NULL DEFAULT 0,
    restored_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    baseline_only INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reconciliation_decisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    base_job_id TEXT NOT NULL DEFAULT '',
    application_id TEXT NOT NULL DEFAULT '',
    decision_type TEXT NOT NULL,
    old_status TEXT NOT NULL DEFAULT '',
    new_status TEXT NOT NULL DEFAULT '',
    old_signal TEXT NOT NULL DEFAULT '',
    new_signal TEXT NOT NULL DEFAULT '',
    reason_code TEXT NOT NULL,
    recoverable INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES reconciliation_runs(id)
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
CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    provider TEXT,
    slug TEXT,
    status TEXT NOT NULL,
    item_count INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    status_code INTEGER,
    detail TEXT,
    checked_at TEXT
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
CREATE TABLE IF NOT EXISTS company_contacts (
    company TEXT PRIMARY KEY,
    domain TEXT,
    contacts_json TEXT,
    discovered_at TEXT
);
CREATE TABLE IF NOT EXISTS company_monitors (
    id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    slug TEXT NOT NULL DEFAULT '',
    careers_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'removed')),
    resolution_status TEXT NOT NULL DEFAULT 'unresolved'
        CHECK (resolution_status IN ('resolved', 'unresolved', 'unsupported')),
    origins_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_success_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS company_monitor_jobs (
    monitor_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (monitor_id, job_id)
);
CREATE TABLE IF NOT EXISTS job_reviews (
    job_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'saved', 'dismissed')),
    origins_json TEXT NOT NULL DEFAULT '[]',
    first_seen TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_mail_events_job ON mail_events(job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_monitors_board
    ON company_monitors(provider, slug)
    WHERE provider <> '' AND slug <> '';
CREATE INDEX IF NOT EXISTS idx_company_monitor_jobs_job
    ON company_monitor_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_job_reviews_state
    ON job_reviews(state);
CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_started
    ON reconciliation_runs(started_at DESC, status);
CREATE INDEX IF NOT EXISTS idx_reconciliation_decisions_run
    ON reconciliation_decisions(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_reconciliation_decisions_application
    ON reconciliation_decisions(application_id);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _harden_perms(path: str) -> None:
    """Best-effort: restrict the DB file (0600) and its data dir (0700) to the
    owner. On POSIX this enforces owner-only access; on Windows ``os.chmod`` only
    toggles the read-only bit, so it's effectively a no-op there (see SECURITY.md
    for NTFS ACL guidance). Never fatal -- permission tightening is defense in depth.
    """
    for target, mode in ((path, 0o600),
                         (os.path.dirname(os.path.abspath(path)), 0o700)):
        try:
            os.chmod(target, mode)
        except OSError:
            pass


class _StoreBase:
    def __init__(self, path: str):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        existing_tables = {
            row["name"] for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        seed_audit_baseline = (
            "applications" in existing_tables and
            "reconciliation_runs" not in existing_tables
        )
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._ensure_columns()
        if seed_audit_baseline:
            self._seed_reconciliation_baseline()
        _harden_perms(path)

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
        for col in ("company", "title", "source", "outreach_at", "outreach_to",
                    "interview_at", "salary_offered", "offer_accepted",
                    "tombstoned_at", "tombstone_reason", "reconciliation_run_id"):
            if col not in appc:
                self.conn.execute(f"ALTER TABLE applications ADD COLUMN {col} TEXT")
        if "reconciliation_exempt" not in appc:
            self.conn.execute(
                "ALTER TABLE applications ADD COLUMN reconciliation_exempt "
                "INTEGER NOT NULL DEFAULT 0"
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_applications_tombstone "
            "ON applications(tombstoned_at, reconciliation_exempt)"
        )
        self.conn.commit()

    def _seed_reconciliation_baseline(self) -> None:
        """Record current counts once when a pre-audit database is upgraded."""
        applications = self.conn.execute(
            "SELECT COUNT(*) AS count FROM applications "
            "WHERE COALESCE(tombstoned_at, '') = ''"
        ).fetchone()["count"]
        tombstones = self.conn.execute(
            "SELECT COUNT(*) AS count FROM applications "
            "WHERE COALESCE(tombstoned_at, '') <> ''"
        ).fetchone()["count"]
        events = self.conn.execute(
            "SELECT COUNT(*) AS count FROM mail_events"
        ).fetchone()["count"]
        timestamp = now_iso()
        self.conn.execute(
            "INSERT OR IGNORE INTO reconciliation_runs ("
            "id, action, initiator, started_at, completed_at, status, "
            "applications_before, applications_after, events_before, events_after, "
            "tombstoned_count, schema_version, baseline_only) "
            "VALUES ('reconcile:baseline:v1', 'recompute', 'cli', ?, ?, 'completed', "
            "?, ?, ?, ?, ?, 1, 1)",
            (
                timestamp, timestamp, applications, applications,
                events, events, tombstones,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "_StoreBase":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _row_to_job(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["is_remote"] = bool(d.get("is_remote"))
    d["raw_is_remote"] = None if d.get("raw_is_remote") is None else bool(d.get("raw_is_remote"))
    return Job.from_dict(d)
