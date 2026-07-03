"""Profile / named base resumes (supports multiple named base resumes)."""
from __future__ import annotations

import json
from typing import Optional

from ..model import Resume
from .base import now_iso


class ProfileMixin:
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
