"""Local persistence for individually approved outreach campaigns."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Optional

from .base import now_iso

_DEFAULT_WEIGHTS = {"region": 0.5, "compensation": 0.3, "growth": 0.2}
MAX_CAMPAIGN_DAILY_LIMIT = 10
MAX_CAMPAIGN_TARGETS = 100
MIN_CAMPAIGN_SPACING_HOURS = 1.0


def _file_sha256(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _approval_hash(row: dict) -> str:
    approved = {
        "selected_email": row.get("selected_email") or "",
        "subject": row.get("subject") or "",
        "body": row.get("body") or "",
        "resume_path": row.get("resume_path") or "",
        "resume_sha256": row.get("resume_sha256") or "",
    }
    return hashlib.sha256(_json(approved).encode("utf-8")).hexdigest()


def _target_id(campaign_id: str, company_key: str) -> str:
    digest = hashlib.sha256(f"{campaign_id}\0{company_key}".encode("utf-8")).hexdigest()[:24]
    return f"campaign-target:{digest}"


def _hydrate(row) -> Optional[dict]:
    if row is None:
        return None
    value = dict(row)
    for key in ("weights_json", "criteria_json", "evidence_json", "contacts_json",
                "summary_json"):
        if key in value:
            default = "[]" if key == "contacts_json" else "{}"
            value[key.removesuffix("_json")] = json.loads(value.pop(key) or default)
    return value


class OutreachCampaignsMixin:
    def create_outreach_campaign(
        self,
        name: str,
        requested_count: int,
        *,
        sector: str = "cybersecurity",
        region: str = "India",
        weights: Optional[dict] = None,
        criteria: Optional[dict] = None,
        resume_name: str = "",
        daily_limit: int = 2,
        min_spacing_hours: float = 4,
        timezone: str = "Asia/Kolkata",
        send_window_start: str = "10:00",
        send_window_end: str = "17:00",
        campaign_id: str = "",
    ) -> dict:
        """Create a draft campaign. No discovery or sending occurs here."""
        if not 1 <= requested_count <= MAX_CAMPAIGN_TARGETS:
            raise ValueError(
                f"requested_count must be between 1 and {MAX_CAMPAIGN_TARGETS}"
            )
        if not 1 <= daily_limit <= MAX_CAMPAIGN_DAILY_LIMIT:
            raise ValueError(
                f"daily_limit must be between 1 and {MAX_CAMPAIGN_DAILY_LIMIT}"
            )
        if min_spacing_hours < MIN_CAMPAIGN_SPACING_HOURS:
            raise ValueError(
                f"min_spacing_hours must be at least {MIN_CAMPAIGN_SPACING_HOURS:g}"
            )
        campaign_id = campaign_id or f"campaign:{uuid.uuid4().hex}"
        timestamp = now_iso()
        self.conn.execute(
            "INSERT INTO outreach_campaigns ("
            "id, name, sector, region, requested_count, weights_json, criteria_json, "
            "resume_name, daily_limit, min_spacing_hours, timezone, send_window_start, "
            "send_window_end, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id, (name or "Outreach campaign").strip(), sector, region,
                requested_count, _json(weights or _DEFAULT_WEIGHTS), _json(criteria or {}),
                resume_name, daily_limit, min_spacing_hours, timezone,
                send_window_start, send_window_end, timestamp, timestamp,
            ),
        )
        self.conn.commit()
        return self.get_outreach_campaign(campaign_id)

    def get_outreach_campaign(self, campaign_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM outreach_campaigns WHERE id = ?", (campaign_id,),
        ).fetchone()
        return _hydrate(row)

    def outreach_campaigns(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM outreach_campaigns ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return [_hydrate(row) for row in rows]

    def set_outreach_campaign_status(self, campaign_id: str, status: str) -> dict:
        allowed = {"draft", "active", "paused", "completed", "cancelled"}
        if status not in allowed:
            raise ValueError(f"invalid campaign status: {status}")
        self.conn.execute(
            "UPDATE outreach_campaigns SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), campaign_id),
        )
        self.conn.commit()
        campaign = self.get_outreach_campaign(campaign_id)
        if campaign is None:
            raise KeyError(campaign_id)
        return campaign

    def delete_draft_outreach_campaign(self, campaign_id: str) -> dict:
        campaign = self.get_outreach_campaign(campaign_id)
        if campaign is None:
            raise KeyError(campaign_id)
        if campaign["status"] != "draft":
            raise ValueError("only draft campaigns can be deleted")
        delivery = self.conn.execute(
            "SELECT 1 FROM outreach_campaign_targets WHERE campaign_id = ? AND ("
            "state IN ('sent', 'replied', 'opted_out') OR "
            "COALESCE(sent_at, '') <> '' OR COALESCE(replied_at, '') <> '' OR "
            "error_code IN ('sending', 'delivery_unknown')) LIMIT 1",
            (campaign_id,),
        ).fetchone()
        sent_run = self.conn.execute(
            "SELECT 1 FROM outreach_campaign_runs "
            "WHERE campaign_id = ? AND sent_count > 0 LIMIT 1",
            (campaign_id,),
        ).fetchone()
        if delivery is not None or sent_run is not None:
            raise ValueError("campaign has delivery history and cannot be deleted")
        with self.conn:
            self.conn.execute(
                "DELETE FROM outreach_campaign_runs WHERE campaign_id = ?", (campaign_id,),
            )
            self.conn.execute(
                "DELETE FROM outreach_campaign_targets WHERE campaign_id = ?", (campaign_id,),
            )
            self.conn.execute("DELETE FROM outreach_campaigns WHERE id = ?", (campaign_id,))
        return campaign

    def upsert_outreach_campaign_target(
        self,
        campaign_id: str,
        company: str,
        company_key: str,
        *,
        rank_score: float = 0,
        region_score: float = 0,
        compensation_score: float = 0,
        growth_score: float = 0,
        evidence_coverage: float = 0,
        evidence: Optional[dict] = None,
        state: str = "ranked",
    ) -> dict:
        timestamp = now_iso()
        target_id = _target_id(campaign_id, company_key)
        self.conn.execute(
            "INSERT INTO outreach_campaign_targets ("
            "id, campaign_id, company_key, company, state, rank_score, region_score, "
            "compensation_score, growth_score, evidence_coverage, evidence_json, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(campaign_id, company_key) DO UPDATE SET "
            "company = excluded.company, rank_score = excluded.rank_score, "
            "region_score = excluded.region_score, "
            "compensation_score = excluded.compensation_score, "
            "growth_score = excluded.growth_score, "
            "evidence_coverage = excluded.evidence_coverage, "
            "evidence_json = excluded.evidence_json, updated_at = excluded.updated_at",
            (
                target_id, campaign_id, company_key, company, state, rank_score,
                region_score, compensation_score, growth_score, evidence_coverage,
                _json(evidence or {}), timestamp, timestamp,
            ),
        )
        self.conn.execute(
            "UPDATE outreach_campaigns SET updated_at = ? WHERE id = ?",
            (timestamp, campaign_id),
        )
        self.conn.commit()
        target = self.get_outreach_campaign_target(target_id)
        if target is None:
            raise RuntimeError("campaign target was not stored")
        return target

    def outreach_campaign_targets(self, campaign_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM outreach_campaign_targets WHERE campaign_id = ? "
            "ORDER BY rank_score DESC, company COLLATE NOCASE, id",
            (campaign_id,),
        ).fetchall()
        return [_hydrate(row) for row in rows]

    def get_outreach_campaign_target(self, target_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM outreach_campaign_targets WHERE id = ?", (target_id,),
        ).fetchone()
        return _hydrate(row)

    def set_outreach_campaign_draft(
        self,
        target_id: str,
        *,
        selected_email: str,
        subject: str,
        body: str,
        resume_path: str = "",
        domain: str = "",
        contacts: Optional[list[dict]] = None,
        selected_source: str = "",
        selected_confidence: str = "",
        selected_note: str = "",
    ) -> dict:
        """Save editable content and invalidate any approval for the old content."""
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = 'draft', domain = ?, "
            "contacts_json = ?, selected_email = ?, selected_source = ?, "
            "selected_confidence = ?, selected_note = ?, subject = ?, body = ?, "
            "resume_path = ?, resume_sha256 = ?, approval_hash = '', approved_at = '', scheduled_at = '', "
            "error_code = '', error_detail = '', updated_at = ? WHERE id = ? "
            "AND COALESCE(error_code, '') <> 'sending'",
            (
                domain, _json(contacts or []), selected_email.strip().lower(),
                selected_source, selected_confidence, selected_note, subject, body,
                resume_path, _file_sha256(resume_path), now_iso(), target_id,
            ),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            if self.get_outreach_campaign_target(target_id) is None:
                raise KeyError(target_id)
            raise ValueError("target send is in progress")
        target = self.get_outreach_campaign_target(target_id)
        if target is None:
            raise KeyError(target_id)
        return target

    def set_outreach_campaign_contacts(
        self, target_id: str, *, domain: str, contacts: list[dict],
        state: str = "needs_contact",
    ) -> dict:
        if state not in {"needs_contact", "draft"}:
            raise ValueError(f"invalid contact discovery state: {state}")
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = ?, domain = ?, contacts_json = ?, "
            "selected_email = '', selected_source = '', selected_confidence = '', "
            "selected_note = '', subject = '', body = '', resume_path = '', "
            "resume_sha256 = '', approval_hash = '', approved_at = '', scheduled_at = '', "
            "updated_at = ? "
            "WHERE id = ? AND COALESCE(error_code, '') <> 'sending'",
            (state, domain, _json(contacts), now_iso(), target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            if self.get_outreach_campaign_target(target_id) is None:
                raise KeyError(target_id)
            raise ValueError("target send is in progress")
        target = self.get_outreach_campaign_target(target_id)
        if target is None:
            raise KeyError(target_id)
        return target

    def approve_outreach_campaign_target(self, target_id: str) -> dict:
        target = self.get_outreach_campaign_target(target_id)
        if target is None:
            raise KeyError(target_id)
        if not target["selected_email"] or not target["subject"] or not target["body"]:
            raise ValueError("recipient, subject, and body are required before approval")
        timestamp = now_iso()
        digest = _approval_hash(target)
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = 'approved', approval_hash = ?, "
            "approved_at = ?, updated_at = ? WHERE id = ? AND state = 'draft' "
            "AND COALESCE(error_code, '') <> 'sending'",
            (digest, timestamp, timestamp, target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("only an editable draft can be approved")
        return self.get_outreach_campaign_target(target_id)

    def outreach_campaign_approval_valid(self, target_id: str) -> bool:
        target = self.get_outreach_campaign_target(target_id)
        return bool(
            target and target["state"] == "approved" and target["approval_hash"]
            and target["approval_hash"] == _approval_hash(target)
        )

    def schedule_outreach_campaign_target(self, target_id: str, scheduled_at: str) -> dict:
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET scheduled_at = ?, updated_at = ? "
            "WHERE id = ? AND state = 'approved'",
            (scheduled_at, now_iso(), target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("only an approved target can be scheduled")
        return self.get_outreach_campaign_target(target_id)

    def set_outreach_campaign_target_state(
        self, target_id: str, state: str, *, error_code: str = "",
        error_detail: str = "",
    ) -> dict:
        allowed = {
            "ranked", "needs_contact", "draft", "approved", "sent", "skipped",
            "failed", "replied", "opted_out",
        }
        if state not in allowed:
            raise ValueError(f"invalid campaign target state: {state}")
        claimed_transition = state == "failed"
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = ?, error_code = ?, "
            "error_detail = ?, updated_at = ? WHERE id = ?" +
            ("" if claimed_transition else " AND COALESCE(error_code, '') <> 'sending'"),
            (state, error_code, error_detail[:500], now_iso(), target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            if self.get_outreach_campaign_target(target_id) is None:
                raise KeyError(target_id)
            raise ValueError("target send is in progress")
        return self.get_outreach_campaign_target(target_id)

    def mark_outreach_campaign_target_sent(self, target_id: str, sent_at: str = "") -> dict:
        timestamp = sent_at or now_iso()
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = 'sent', sent_at = ?, "
            "error_code = '', error_detail = '', updated_at = ? "
            "WHERE id = ? AND state = 'approved' AND error_code = 'sending'",
            (timestamp, timestamp, target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("only a claimed approved target can be marked sent")
        return self.get_outreach_campaign_target(target_id)

    def mark_outreach_campaign_delivery_unknown(
        self, target_id: str, detail: str,
    ) -> dict:
        """Lock a claimed attempt whose external SMTP outcome cannot be known."""
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET error_code = 'delivery_unknown', "
            "error_detail = ?, updated_at = ? WHERE id = ? AND state = 'approved' "
            "AND error_code = 'sending'",
            (detail[:200], now_iso(), target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("only a claimed target can enter delivery unknown")
        return self.get_outreach_campaign_target(target_id)

    def resolve_outreach_campaign_delivery(
        self, target_id: str, outcome: str, resolved_at: str = "",
    ) -> dict:
        """Resolve an unknown SMTP outcome only after the user checks Sent mail."""
        timestamp = resolved_at or now_iso()
        if outcome == "sent":
            sql = (
                "UPDATE outreach_campaign_targets SET state = 'sent', sent_at = ?, "
                "error_code = '', error_detail = '', updated_at = ? "
                "WHERE id = ? AND state = 'approved' AND error_code = 'delivery_unknown'"
            )
            params = (timestamp, timestamp, target_id)
        elif outcome == "not_sent":
            sql = (
                "UPDATE outreach_campaign_targets SET state = 'draft', approval_hash = '', "
                "approved_at = '', scheduled_at = '', error_code = '', error_detail = '', "
                "updated_at = ? WHERE id = ? AND state = 'approved' "
                "AND error_code = 'delivery_unknown'"
            )
            params = (timestamp, target_id)
        else:
            raise ValueError("delivery outcome must be sent or not_sent")
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("target is not awaiting delivery resolution")
        return self.get_outreach_campaign_target(target_id)

    def claim_outreach_campaign_target_send(
        self, target_id: str, outbound_message_id: str = "",
    ) -> bool:
        """Atomically claim an approved target so two senders cannot both email it."""
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET error_code = 'sending', error_detail = '', "
            "outbound_message_id = ?, updated_at = ? WHERE id = ? AND state = 'approved' "
            "AND approval_hash <> '' AND COALESCE(error_code, '') = ''",
            (outbound_message_id.strip().strip("<>"), now_iso(), target_id),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def due_outreach_campaign_targets(self, due_at: str, *, campaign_id: str = "") -> list[dict]:
        params: list[str] = [due_at]
        campaign_filter = ""
        if campaign_id:
            campaign_filter = " AND t.campaign_id = ?"
            params.append(campaign_id)
        rows = self.conn.execute(
            "SELECT t.* FROM outreach_campaign_targets t "
            "JOIN outreach_campaigns c ON c.id = t.campaign_id "
            "WHERE c.status = 'active' AND t.state = 'approved' "
            "AND COALESCE(t.error_code, '') = '' "
            "AND t.scheduled_at <> '' AND t.scheduled_at <= ?" + campaign_filter +
            " ORDER BY t.scheduled_at, t.approved_at, t.id",
            params,
        ).fetchall()
        return [_hydrate(row) for row in rows]

    def sent_outreach_campaign_targets(self, *, start_at: str = "", end_at: str = "",
                                       company_key: str = "") -> list[dict]:
        where = ["state IN ('sent', 'replied', 'opted_out')", "sent_at <> ''"]
        params: list[str] = []
        if start_at:
            where.append("sent_at >= ?")
            params.append(start_at)
        if end_at:
            where.append("sent_at < ?")
            params.append(end_at)
        if company_key:
            where.append("company_key = ?")
            params.append(company_key)
        rows = self.conn.execute(
            "SELECT * FROM outreach_campaign_targets WHERE " + " AND ".join(where) +
            " ORDER BY sent_at DESC, id",
            params,
        ).fetchall()
        return [_hydrate(row) for row in rows]

    def last_outreach_campaign_sent_at(self, company_key: str = "") -> str:
        where = "WHERE state IN ('sent', 'replied', 'opted_out') AND sent_at <> ''"
        params: tuple[str, ...] = ()
        if company_key:
            where += " AND company_key = ?"
            params = (company_key,)
        row = self.conn.execute(
            f"SELECT MAX(sent_at) AS last FROM outreach_campaign_targets {where}", params,
        ).fetchone()
        return str(row["last"] or "") if row else ""

    def mark_outreach_campaign_target_reply(
        self, target_id: str, replied_at: str, *, event_id: str,
        opted_out: bool = False,
    ) -> dict:
        state = "opted_out" if opted_out else "replied"
        cursor = self.conn.execute(
            "UPDATE outreach_campaign_targets SET state = ?, replied_at = ?, "
            "reply_event_id = ?, updated_at = ? "
            "WHERE id = ? AND state = 'sent'",
            (state, replied_at, event_id, now_iso(), target_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("only a sent target can be marked replied")
        return self.get_outreach_campaign_target(target_id)

    def add_outreach_suppression(
        self, kind: str, value: str, *, reason: str = "", source: str = "",
    ) -> dict:
        if kind not in {"email", "domain", "company"}:
            raise ValueError(f"invalid suppression kind: {kind}")
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("suppression value is required")
        suppression_id = f"suppression:{kind}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"
        self.conn.execute(
            "INSERT INTO outreach_suppressions (id, kind, value, reason, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(kind, value) DO UPDATE SET "
            "reason = excluded.reason, source = excluded.source",
            (suppression_id, kind, normalized, reason[:200], source[:200], now_iso()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM outreach_suppressions WHERE kind = ? AND value = ?",
            (kind, normalized),
        ).fetchone()
        return dict(row)

    def is_outreach_suppressed(self, kind: str, value: str) -> bool:
        normalized = (value or "").strip().lower()
        if not normalized:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM outreach_suppressions WHERE kind = ? AND value = ?",
            (kind, normalized),
        ).fetchone()
        return row is not None

    def outreach_suppressions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM outreach_suppressions ORDER BY created_at DESC, id"
        ).fetchall()
        return [dict(row) for row in rows]

    def outreach_campaign_history(self, campaign_id: str = "") -> list[dict]:
        """Sent messages joined to their immutable inbound reply event, when any."""
        campaign_filter = ""
        params: tuple[str, ...] = ()
        if campaign_id:
            campaign_filter = " AND t.campaign_id = ?"
            params = (campaign_id,)
        rows = self.conn.execute(
            "SELECT t.id AS target_id, t.campaign_id, t.company, t.selected_email AS recipient, "
            "t.subject, t.state, t.outbound_message_id, t.sent_at, t.replied_at, "
            "t.reply_event_id, m.from_addr AS reply_from, m.subject AS reply_subject, "
            "m.signal AS reply_signal, m.date AS reply_date "
            "FROM outreach_campaign_targets t "
            "LEFT JOIN mail_events m ON m.id = t.reply_event_id "
            "WHERE (t.sent_at <> '' OR t.error_code IN ('sending', 'delivery_unknown'))" +
            campaign_filter +
            " ORDER BY COALESCE(NULLIF(t.sent_at, ''), t.updated_at) DESC, t.id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]