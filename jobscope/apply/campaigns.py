"""Individually approved campaigns with an encrypted read-only snapshot."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jobscope.apply import outreach
from jobscope.apply.company_rank import is_security_role, rank_companies
from jobscope.core.model import Job
from jobscope.core.store.monitoring import normalize_company_key
from jobscope.core.store.outreach_campaigns import MAX_CAMPAIGN_DAILY_LIMIT

_STALE_SEND_CLAIM = timedelta(minutes=15)
OUTREACH_SNAPSHOT_META_KEY = "campaign:snapshot:v1"
OUTREACH_POLICY_VERSION = "outreach-policy-v1"
_RECIPIENT_KINDS = {
    "prior_inbound_recruiter", "employer_published", "verified_business_contact",
    "role_inbox",
}
_PURPOSES = {"cold", "followup"}
_BASES = {"consent", "existing_relationship", "legitimate_interest"}
_OPTOUT_METHODS = {"reply", "mailto", "unsubscribe_link"}
_SOURCE_RECIPIENT_KIND = {
    "recruiter": "prior_inbound_recruiter",
    "mail_event": "prior_inbound_recruiter",
    "prior_cold": "prior_inbound_recruiter",
    "prior_outreach": "prior_inbound_recruiter",
    "discovered": "employer_published",
    "hunter": "verified_business_contact",
    "apollo": "verified_business_contact",
    "override": "verified_business_contact",
    "role_inbox": "role_inbox",
}


def _utc(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _file_sha256(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Kolkata":
            return timezone(timedelta(hours=5, minutes=30), name)
        if name in {"UTC", "Etc/UTC"}:
            return timezone.utc
        raise ValueError(f"unknown campaign timezone: {name}") from None


def _clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ValueError(f"invalid campaign send time: {value}") from None


def _campaign_defaults(cfg: dict) -> dict:
    return (cfg.get("apply", {}).get("outreach", {}).get("campaign", {}) or {})


def normalize_policy(policy: dict, *, target: dict, campaign: dict) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("compliance policy review is required")

    def required(name: str) -> str:
        value = str(policy.get(name) or "").strip()
        if not value or value.casefold() == "unknown":
            raise ValueError(f"policy {name.replace('_', ' ')} is required")
        return value

    sender_jurisdiction = required("sender_jurisdiction").upper()
    recipient_jurisdiction = required("recipient_jurisdiction").upper()
    recipient_kind = required("recipient_kind").lower()
    contact_source = required("contact_source").lower()
    contact_provenance_at = required("contact_provenance_at")
    purpose = required("purpose").lower()
    basis = required("basis").lower()
    opt_out_method = required("opt_out_method").lower()
    reviewer = required("reviewer")
    policy_version = required("policy_version")
    identity_footer = policy.get("identity_footer") is True
    consent = str(policy.get("consent") or "").strip().lower()

    if len(sender_jurisdiction) > 80 or len(recipient_jurisdiction) > 80:
        raise ValueError("policy jurisdiction is too long")
    if recipient_kind not in _RECIPIENT_KINDS:
        raise ValueError("policy recipient kind is invalid")
    expected_kind = _SOURCE_RECIPIENT_KIND.get(contact_source)
    if expected_kind is None or recipient_kind != expected_kind:
        raise ValueError("policy recipient kind does not match the contact source")
    if purpose not in _PURPOSES or purpose != str(campaign.get("purpose") or "cold"):
        raise ValueError("policy purpose does not match the campaign")
    if basis not in _BASES:
        raise ValueError("policy basis is invalid")
    if consent not in {"yes", "no", "not_applicable"}:
        raise ValueError("policy consent decision is required")
    if basis == "consent" and consent != "yes":
        raise ValueError("consent basis requires affirmative consent")
    if opt_out_method not in _OPTOUT_METHODS:
        raise ValueError("policy opt-out method is invalid")
    if not identity_footer:
        raise ValueError("policy identity/footer confirmation is required")
    if policy_version != OUTREACH_POLICY_VERSION:
        raise ValueError("policy version is unsupported")
    if contact_source != str(target.get("selected_source") or "").strip().lower():
        raise ValueError("policy contact source does not match the selected contact")
    if _parse_iso(contact_provenance_at) is None:
        raise ValueError("policy contact provenance date must be ISO-8601")

    return {
        "sender_jurisdiction": sender_jurisdiction,
        "recipient_jurisdiction": recipient_jurisdiction,
        "recipient_kind": recipient_kind,
        "contact_source": contact_source,
        "contact_provenance_at": _iso(_parse_iso(contact_provenance_at)),
        "purpose": purpose,
        "basis": basis,
        "consent": consent,
        "identity_footer": True,
        "opt_out_method": opt_out_method,
        "reviewer": reviewer[:200],
        "policy_version": OUTREACH_POLICY_VERSION,
    }


def _summary_state(target: dict) -> str:
    return (
        "delivery_unknown"
        if target.get("error_code") == "delivery_unknown"
        else target["state"]
    )


def get_campaign_detail(store, campaign_id: str) -> dict:
    campaign = store.get_outreach_campaign(campaign_id)
    if campaign is None:
        raise KeyError(campaign_id)
    targets = store.outreach_campaign_targets(campaign_id)
    counts: dict[str, int] = {}
    for target in targets:
        state = _summary_state(target)
        counts[state] = counts.get(state, 0) + 1
    return {
        "campaign": campaign,
        "targets": targets,
        "counts": counts,
        "history": store.outreach_campaign_history(campaign_id),
        "reply_tracking": {
            "last_checked_at": store.meta_get("campaign:replies:last_checked_at", "") or "",
            "last_status": store.meta_get("campaign:replies:last_status", "") or "",
        },
    }


def list_campaigns(store) -> list[dict]:
    result = []
    for campaign in store.outreach_campaigns():
        targets = store.outreach_campaign_targets(campaign["id"])
        counts: dict[str, int] = {}
        for target in targets:
            state = _summary_state(target)
            counts[state] = counts.get(state, 0) + 1
        delivered = sum(counts.get(state, 0) for state in ("sent", "replied", "opted_out"))
        responses = sum(counts.get(state, 0) for state in ("replied", "opted_out"))
        result.append({
            **campaign, "counts": counts, "target_count": len(targets),
            "delivered_count": delivered, "response_count": responses,
        })
    return result


def outreach_snapshot(store) -> dict:
    """Allowlisted read model for the passphrase-encrypted Pages payload."""
    summaries = list_campaigns(store)
    if not summaries:
        cached = store.meta_get(OUTREACH_SNAPSHOT_META_KEY, "") or ""
        if cached:
            import json
            try:
                value = json.loads(cached)
            except (TypeError, json.JSONDecodeError):
                value = None
            if isinstance(value, dict) and value.get("read_only") is True:
                return value

    campaign_keys = {
        "id", "name", "purpose", "status", "sector", "region",
        "requested_count", "weights", "criteria", "resume_name",
        "daily_limit", "min_spacing_hours",
        "timezone", "send_window_start", "send_window_end", "created_at",
        "updated_at", "counts", "target_count", "delivered_count",
        "response_count",
    }
    target_keys = {
        "id", "campaign_id", "company", "state", "rank_score",
        "region_score", "compensation_score", "growth_score",
        "evidence_coverage", "evidence", "selected_email", "selected_source",
        "selected_confidence", "subject", "approved_at", "scheduled_at",
        "sent_at", "replied_at", "error_code", "created_at", "updated_at",
        "followup_number", "recipient_locked",
    }
    history_keys = {
        "target_id", "campaign_id", "company", "recipient", "subject",
        "state", "sent_at", "replied_at", "reply_from", "reply_subject",
        "reply_signal", "reply_date",
    }
    details = []
    for summary in summaries:
        detail = get_campaign_detail(store, summary["id"])
        details.append({
            "campaign_id": summary["id"],
            "targets": [
                {key: target.get(key) for key in target_keys}
                for target in detail["targets"]
            ],
            "history": [
                {key: item.get(key) for key in history_keys}
                for item in detail["history"]
            ],
            "reply_tracking": detail["reply_tracking"],
        })
    return {
        "read_only": True,
        "campaigns": [
            {key: summary.get(key) for key in campaign_keys}
            for summary in summaries
        ],
        "details": details,
        "engagements": engagement_activity(store),
    }


def engagement_activity(store) -> list[dict]:
    """Project application and cold outreach into privacy-safe activity threads."""
    from jobscope.deliver.render import _summarize

    groups: dict[str, dict] = {}
    seen_replies: set[str] = set()
    campaign_sends: set[tuple[str, str, str]] = set()
    rows = store.outreach_engagement_rows()
    rows_by_id = {str(row.get("target_id") or ""): row for row in rows}

    def lineage(row: dict) -> tuple[str, str]:
        """Return inherited application ID and stable root target, cycle-safe."""
        current = row
        application_job_id = ""
        visited: list[str] = []
        while True:
            target_id = str(current.get("target_id") or "")
            if target_id in visited:
                return application_job_id, min(visited or [target_id])
            visited.append(target_id)
            application_job_id = (
                application_job_id or str(current.get("application_job_id") or "")
            )
            source_target_id = str(current.get("source_target_id") or "")
            if not source_target_id:
                return application_job_id, target_id
            parent = rows_by_id.get(source_target_id)
            if parent is None:
                return application_job_id, source_target_id
            current = parent

    def event_sort_key(event: dict) -> tuple[float, int, str]:
        parsed = _parse_iso(str(event.get("date") or ""))
        timestamp = parsed.timestamp() if parsed is not None else float("-inf")
        direction = 1 if event.get("direction") == "inbound" else 0
        return timestamp, direction, str(event.get("date") or "")

    def send_identity(application_job_id: str, sent_at: str, recipient: str) -> tuple[str, str, str]:
        parsed = _parse_iso(sent_at)
        canonical_sent_at = _iso(parsed) if parsed is not None else sent_at.strip()
        return application_job_id, canonical_sent_at, recipient.strip().casefold()

    def thread(key: str, *, kind: str, application_job_id: str = "",
               company: str = "", title: str = "") -> dict:
        return groups.setdefault(key, {
            "id": key,
            "kind": kind,
            "application_job_id": application_job_id,
            "company": company,
            "title": title,
            "campaign_id": "",
            "target_id": "",
            "recipient": "",
            "subject": "",
            "state": "",
            "sent_at": "",
            "latest_activity_at": "",
            "followup_count": 0,
            "outbound_count": 0,
            "reply_count": 0,
            "events": [],
        })

    for row in rows:
        application_job_id, root_target_id = lineage(row)
        target_id = str(row.get("target_id") or "")
        kind = "application" if application_job_id else "cold"
        key = (f"application:{application_job_id}" if application_job_id
               else f"cold:{root_target_id or target_id}")
        current = thread(
            key, kind=kind, application_job_id=application_job_id,
            company=str(row.get("company") or ""), title=str(row.get("title") or ""),
        )
        event_kind = "cold" if row.get("purpose") == "cold" else "followup"
        date_value = str(row.get("sent_at") or row.get("updated_at") or "")
        state = str(row.get("error_code") or row.get("state") or "")
        outbound = {
            "direction": "outbound",
            "kind": event_kind,
            "date": date_value,
            "subject": str(row.get("subject") or ""),
            "participant": str(row.get("recipient") or ""),
            "summary": "",
            "state": state,
            "signal": "",
            "followup_number": int(row.get("followup_number") or 0),
            "campaign_id": str(row.get("campaign_id") or ""),
            "target_id": target_id,
        }
        current["events"].append(outbound)
        campaign_sends.add(send_identity(
            application_job_id, date_value, str(outbound["participant"]),
        ))

        reply_event_id = str(row.get("reply_event_id") or "")
        if reply_event_id and reply_event_id not in seen_replies:
            seen_replies.add(reply_event_id)
            current["events"].append({
                "direction": "inbound",
                "kind": "opt_out" if row.get("state") == "opted_out" else "reply",
                "date": str(row.get("reply_date") or row.get("replied_at") or ""),
                "subject": str(row.get("reply_subject") or ""),
                "participant": str(row.get("reply_from") or ""),
                "summary": _summarize(str(row.get("reply_snippet") or "")),
                "state": str(row.get("state") or ""),
                "signal": str(row.get("reply_signal") or ""),
                "followup_number": int(row.get("followup_number") or 0),
                "campaign_id": str(row.get("campaign_id") or ""),
                "target_id": target_id,
            })

    for application in store.applications():
        sent_at = str(application.get("outreach_at") or "")
        if not sent_at:
            continue
        job_id = str(application.get("job_id") or "")
        recipient = str(application.get("outreach_to") or "")
        if send_identity(job_id, sent_at, recipient) in campaign_sends:
            continue
        current = thread(
            f"application:{job_id}", kind="application", application_job_id=job_id,
            company=str(application.get("company") or ""),
            title=str(application.get("title") or ""),
        )
        current["events"].append({
            "direction": "outbound",
            "kind": "direct",
            "date": sent_at,
            "subject": "",
            "participant": recipient,
            "summary": "",
            "state": "sent",
            "signal": "",
            "followup_number": 0,
            "campaign_id": "",
            "target_id": "",
        })

    for current in groups.values():
        current["events"].sort(key=event_sort_key)
        outbound = [event for event in current["events"] if event["direction"] == "outbound"]
        inbound = [event for event in current["events"] if event["direction"] == "inbound"]
        latest = current["events"][-1]
        latest_outbound = outbound[-1]
        current.update({
            "campaign_id": latest_outbound["campaign_id"],
            "target_id": latest_outbound["target_id"],
            "recipient": latest_outbound["participant"],
            "subject": latest_outbound["subject"],
            "state": latest["state"],
            "sent_at": outbound[0]["date"],
            "latest_activity_at": latest["date"],
            "followup_count": sum(event["kind"] == "followup" for event in outbound),
            "outbound_count": len(outbound),
            "reply_count": len(inbound),
        })

    return sorted(groups.values(), key=lambda item: (
        event_sort_key({"date": item["latest_activity_at"], "direction": "inbound"}),
        item["id"],
    ), reverse=True)


def delete_draft_campaign(store, campaign_id: str) -> dict:
    campaign = store.delete_draft_outreach_campaign(campaign_id)
    return {
        "ok": True,
        "deleted_campaign_id": campaign["id"],
        "deleted_campaign_name": campaign["name"],
    }


def sending_readiness(cfg: dict, store=None) -> dict:
    """Check unattended SMTP prerequisites without exposing secret values."""
    from jobscope.core.config import smtp_password

    errors: list[str] = []
    outreach_cfg = cfg.get("apply", {}).get("outreach", {}) or {}
    email_cfg = cfg.get("email", {}) or {}
    if not outreach_cfg.get("enabled"):
        errors.append("apply.outreach.enabled is false")
    if not email_cfg.get("enabled"):
        errors.append("email.enabled is false")
    for field in ("from_addr", "smtp_host", "smtp_port"):
        if not email_cfg.get(field):
            errors.append(f"email.{field} is missing")
    if not smtp_password(cfg):
        errors.append(
            f"no keychain/environment value for {email_cfg.get('password_env') or 'JOBSCOPE_SMTP_PASSWORD'}"
        )
    if store is not None:
        blocker = store.outreach_campaign_delivery_blocker()
        if blocker:
            errors.append(
                "an outbound delivery is unresolved"
                if blocker == "delivery_unknown"
                else "an outbound delivery is in progress"
            )
        invalid_attachments = 0
        for campaign in store.outreach_campaigns():
            for target in store.outreach_campaign_targets(campaign["id"]):
                if target.get("state") != "approved":
                    continue
                path = str(target.get("resume_path") or "")
                expected = str(target.get("resume_sha256") or "")
                if (not path or not expected or not os.path.isfile(path)
                        or _file_sha256(path) != expected):
                    invalid_attachments += 1
        if invalid_attachments:
            errors.append(
                f"{invalid_attachments} approved target attachment(s) are missing or changed"
            )
    return {"ok": not errors, "errors": errors}


def create_campaign(
    cfg: dict,
    store,
    name: str,
    requested_count: int,
    *,
    candidates: Optional[Iterable[str]] = None,
    weights: Optional[dict] = None,
    resume_name: str = "",
    now: Optional[datetime] = None,
) -> dict:
    defaults = _campaign_defaults(cfg)
    ranking = rank_companies(
        cfg, store, requested_count, candidates=candidates,
        weights=weights or defaults.get("weights"), now=now,
    )
    campaign = store.create_outreach_campaign(
        name, requested_count,
        weights=ranking["weights"],
        criteria={
            "sector": "cybersecurity", "region": "India",
            "follow_up": ranking["follow_up"], "blocked": ranking["blocked"],
        },
        resume_name=resume_name,
        daily_limit=int(defaults.get("daily_limit", 2)),
        min_spacing_hours=float(defaults.get("min_spacing_hours", 4)),
        timezone=str(defaults.get("timezone", "Asia/Kolkata")),
        send_window_start=str(defaults.get("send_window_start", "10:00")),
        send_window_end=str(defaults.get("send_window_end", "17:00")),
    )
    for item in ranking["ranked"]:
        store.upsert_outreach_campaign_target(
            campaign["id"], item["company"], item["company_key"],
            rank_score=item["score"],
            region_score=item["factors"]["region"],
            compensation_score=item["factors"]["compensation"],
            growth_score=item["factors"]["growth"],
            evidence_coverage=item["evidence_coverage"],
            evidence=item["evidence"],
        )
    return {**get_campaign_detail(store, campaign["id"]), "ranking": {
        "eligible_count": ranking["eligible_count"],
        "follow_up": ranking["follow_up"],
        "blocked": ranking["blocked"],
    }}


_FOLLOWUP_RESPONSE_SIGNALS = {
    "recruiter", "assessment", "interview", "offer", "rejection",
    "campaign_reply", "campaign_optout",
}
_FOLLOWUP_BLOCKING_APPLICATION_STATUSES = {
    "interview", "rejected", "offer", "withdrawn", "closed",
}


def _latest_timestamp(*values: str) -> Optional[datetime]:
    parsed = [item for value in values if (item := _parse_iso(value)) is not None]
    return max(parsed) if parsed else None


def _followup_is_due(anchor: Optional[datetime], days: int, now: datetime) -> bool:
    return bool(anchor and _utc(now) - anchor >= timedelta(days=max(1, days)))


def _has_response_after(store, job_id: str, anchor: datetime) -> bool:
    for event in store.mail_events(job_id):
        if (event.get("signal") or "") not in _FOLLOWUP_RESPONSE_SIGNALS:
            continue
        event_at = _parse_iso(event.get("date") or event.get("first_seen") or "")
        if event_at and event_at > anchor:
            return True
    return False


def _followup_job(store, application: dict | None, company: str) -> Job:
    if application:
        job = store.get_job(application.get("job_id") or "")
        if job is not None:
            return job
        return Job(
            source="application", title=application.get("title") or "",
            company=application.get("company") or company,
        )
    return _representative_job(store, company)


def _cached_followup_contact(store, company: str) -> tuple[str, list[dict], dict | None]:
    record = store.get_company_contacts(company) or {}
    domain = str(record.get("domain") or "").strip().lower()
    contacts = outreach.rank_recruiter_contacts(record.get("contacts") or [])
    selected = next((
        contact for contact in contacts
        if (
            contact.get("source") == "recruiter"
            and outreach.valid_recipient(contact.get("email") or "")
        ) or (
            contact.get("source") != "role_inbox"
            and outreach.valid_company_recipient(contact.get("email") or "", domain)
        )
    ), None)
    return domain, contacts, selected


def create_followup_campaign(
    cfg: dict,
    store,
    name: str,
    requested_count: int,
    *,
    resume_name: str = "",
    include_cold: bool = True,
    include_applications: bool = True,
    now: Optional[datetime] = None,
) -> dict:
    """Build one deduplicated, unsent follow-up queue; approval remains individual."""
    if not 1 <= requested_count <= 100:
        raise ValueError("requested_count must be between 1 and 100")
    current = _utc(now)
    followup_days = int((cfg.get("apply", {}) or {}).get("followup_days", 7))
    existing_applications, existing_sources = store.followup_source_ids()
    existing_companies = store.followup_company_keys()

    applications_by_company: dict[str, list[dict]] = {}
    due_apps: dict[str, tuple[dict, datetime]] = {}
    for application in store.applications():
        company_key = normalize_company_key(application.get("company") or "")
        if not company_key:
            continue
        applications_by_company.setdefault(company_key, []).append(application)
        if application.get("status") != "applied":
            continue
        job_id = application.get("job_id") or ""
        if (not job_id or job_id in existing_applications
                or company_key in existing_companies):
            continue
        anchor = _latest_timestamp(
            application.get("applied_at") or "", application.get("outreach_at") or "",
        )
        if not _followup_is_due(anchor, followup_days, current):
            continue
        if anchor and _has_response_after(store, job_id, anchor):
            continue
        previous = due_apps.get(company_key)
        if previous is None or anchor > previous[1]:
            due_apps[company_key] = (application, anchor)

    candidates: list[dict] = []
    used_companies: set[str] = set()
    if include_cold:
        for source in store.sent_outreach_campaign_targets():
            if source.get("state") != "sent" or source["id"] in existing_sources:
                continue
            source_campaign = store.get_outreach_campaign(source["campaign_id"])
            if not source_campaign or source_campaign.get("purpose", "cold") != "cold":
                continue
            company_key = source.get("company_key") or ""
            if (not company_key or company_key in used_companies
                    or company_key in existing_companies):
                continue
            application = None
            application_anchor = None
            related = applications_by_company.get(company_key) or []
            if related:
                latest = max(
                    related,
                    key=lambda item: _parse_iso(item.get("updated") or "")
                    or datetime.min.replace(tzinfo=timezone.utc),
                )
                status = latest.get("status") or ""
                if status in _FOLLOWUP_BLOCKING_APPLICATION_STATUSES:
                    continue
                if status == "applied":
                    application = latest
                    application_anchor = _latest_timestamp(
                        latest.get("applied_at") or "", latest.get("outreach_at") or "",
                    )
                    job_id = latest.get("job_id") or ""
                    if (not application_anchor or job_id in existing_applications
                            or _has_response_after(store, job_id, application_anchor)):
                        continue
            anchor = _latest_timestamp(
                source.get("sent_at") or "",
                application_anchor.isoformat() if application_anchor else "",
            )
            if not _followup_is_due(anchor, followup_days, current):
                continue
            if not source.get("selected_email") or not source.get("outbound_message_id"):
                continue
            candidates.append({
                "company": source["company"], "company_key": company_key,
                "application": application, "source_target": source,
                "anchor": anchor, "source": "cold",
            })
            used_companies.add(company_key)

    if include_applications:
        for company_key, (application, anchor) in sorted(
            due_apps.items(), key=lambda item: item[1][1]
        ):
            if company_key in used_companies:
                continue
            candidates.append({
                "company": application.get("company") or "",
                "company_key": company_key, "application": application,
                "source_target": None, "anchor": anchor, "source": "application",
            })
            used_companies.add(company_key)

    candidates.sort(key=lambda item: item["anchor"])
    candidates = candidates[:requested_count]
    if not candidates:
        raise ValueError("no follow-up candidates are currently due")
    resume = _resume_for_campaign(store, {"resume_name": resume_name})
    if resume is None:
        raise ValueError("upload or select a résumé before drafting campaign outreach")
    if not resume.source_path or not os.path.exists(resume.source_path):
        raise ValueError("the selected résumé file is not available on disk")
    defaults = _campaign_defaults(cfg)
    campaign = store.create_outreach_campaign(
        name, len(candidates), purpose="followup",
        criteria={
            "sources": [
                source for source, enabled in (
                    ("cold", include_cold), ("applications", include_applications),
                ) if enabled
            ],
            "followup_days": followup_days,
        },
        resume_name=resume_name,
        daily_limit=int(defaults.get("daily_limit", 2)),
        min_spacing_hours=float(defaults.get("min_spacing_hours", 4)),
        timezone=str(defaults.get("timezone", "Asia/Kolkata")),
        send_window_start=str(defaults.get("send_window_start", "10:00")),
        send_window_end=str(defaults.get("send_window_end", "17:00")),
    )
    for candidate in candidates:
        application = candidate["application"]
        source = candidate["source_target"]
        recipient = (source or {}).get("selected_email") or (
            application or {}
        ).get("outreach_to") or ""
        domain = (source or {}).get("domain") or (
            recipient.split("@", 1)[1].lower() if "@" in recipient else ""
        )
        contacts: list[dict] = []
        selected: dict | None = None
        recipient_locked = bool(recipient)
        if recipient:
            selected = {
                "email": recipient,
                "source": "prior_cold" if source else "prior_outreach",
                "confidence": "high",
                "note": "locked to the original outreach recipient",
            }
            contacts = [selected]
        else:
            domain, contacts, selected = _cached_followup_contact(
                store, candidate["company"],
            )
        target = store.upsert_outreach_campaign_target(
            campaign["id"], candidate["company"], candidate["company_key"],
            application_job_id=(application or {}).get("job_id") or "",
            source_target_id=(source or {}).get("id") or "",
            parent_message_id=(source or {}).get("outbound_message_id") or "",
            root_message_id=(source or {}).get("root_message_id")
            or (source or {}).get("outbound_message_id") or "",
            followup_number=1, recipient_locked=recipient_locked,
            rank_score=max(0, (current - candidate["anchor"]).days),
            evidence={
                "followup_source": candidate["source"],
                "anchor": _iso(candidate["anchor"]),
            },
            state="needs_contact",
        )
        store.set_outreach_campaign_contacts(
            target["id"], domain=domain, contacts=contacts,
            state="draft" if selected else "needs_contact",
        )
        if selected:
            update_draft(
                cfg, store, target["id"], selected_email=selected["email"],
            )
    return get_campaign_detail(store, campaign["id"])


def _company_url(store, company: str) -> str:
    monitor = store.get_company_monitor(company)
    if monitor and monitor.get("careers_url"):
        return monitor["careers_url"]
    key = normalize_company_key(company)
    for job in store.jobs():
        if normalize_company_key(job.company) == key and job.company_url:
            return job.company_url
    return ""


def _representative_job(store, company: str) -> Job:
    key = normalize_company_key(company)
    for job in store.jobs():
        if (normalize_company_key(job.company) == key
                and (job.status or "open") != "closed"
                and is_security_role(job)):
            return job
    return Job(
        source="campaign", title="Cybersecurity opportunities", company=company,
        description="Cybersecurity engineering, research, and consulting opportunities.",
    )


def _resume_for_campaign(store, campaign: dict):
    name = campaign.get("resume_name") or ""
    return store.get_named_resume(name) if name else store.get_resume()


def discover_target(cfg: dict, store, target_id: str, *, force: bool = False,
                    fetch: bool = True) -> dict:
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    result = outreach.refresh_company_contacts(
        cfg, store, target["company"], url=_company_url(store, target["company"]),
        force=force, fetch=fetch,
    )
    contacts = outreach.rank_recruiter_contacts(result.get("contacts") or [])
    domain = result.get("domain") or ""
    selectable = next(
        (
            contact for contact in contacts
            if contact.get("source") != "role_inbox"
            and outreach.valid_company_recipient(contact.get("email") or "", domain)
        ),
        None,
    )
    if selectable is None:
        return store.set_outreach_campaign_contacts(
            target_id, domain=domain, contacts=contacts,
        )
    store.set_outreach_campaign_contacts(
        target_id, domain=domain, contacts=contacts, state="draft",
    )
    return update_draft(cfg, store, target_id, selected_email=selectable["email"])


def discover_pending_targets(
    cfg: dict, store, campaign_id: str, *, limit: int = 5, fetch: bool = True,
) -> dict:
    """Discover a bounded batch; approval always remains individual."""
    if not 1 <= limit <= 10:
        raise ValueError("contact discovery batch limit must be between 1 and 10")
    get_campaign_detail(store, campaign_id)
    targets = store.outreach_campaign_targets(campaign_id)
    candidates = (
        [target for target in targets if target["state"] == "ranked"]
        + [target for target in targets if target["state"] == "needs_contact"]
        + [target for target in targets
           if target["state"] == "failed"
           and target.get("error_code") == "contact_discovery_failed"]
    )[:limit]
    drafted = needs_contact = failed = 0
    for target in candidates:
        try:
            result = discover_target(
                cfg, store, target["id"],
                force=target["state"] != "ranked", fetch=fetch,
            )
            if result["state"] == "draft":
                drafted += 1
            else:
                needs_contact += 1
        except Exception as exc:  # noqa: BLE001 - one company never stops the batch
            store.set_outreach_campaign_target_state(
                target["id"], "failed", error_code="contact_discovery_failed",
                error_detail=str(exc)[:200],
            )
            failed += 1
    remaining = sum(
        target["state"] == "ranked"
        for target in store.outreach_campaign_targets(campaign_id)
    )
    return {
        "ok": True, "processed": len(candidates), "drafted": drafted,
        "needs_contact": needs_contact, "failed": failed, "remaining": remaining,
    }


def update_draft(
    cfg: dict,
    store,
    target_id: str,
    *,
    selected_email: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> dict:
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    email = (selected_email or "").strip().lower()
    original_email = str(target.get("selected_email") or "").strip().lower()
    if target.get("recipient_locked") and original_email and email != original_email:
        raise ValueError("recipient is locked to the original outreach address")
    contact = next(
        (item for item in target.get("contacts") or []
         if str(item.get("email") or "").strip().lower() == email),
        None,
    )
    if contact is None:
        raise ValueError("select one of the discovered contacts")
    if target.get("recipient_locked"):
        if not outreach.valid_recipient(email):
            raise ValueError("locked recipient must be valid and non-automated")
    elif not outreach.valid_company_recipient(email, target.get("domain") or ""):
        raise ValueError("recipient must be valid, non-automated, and on the company domain")
    resume = _resume_for_campaign(store, campaign)
    if resume is None:
        raise ValueError("upload or select a résumé before drafting campaign outreach")
    resume_path = resume.source_path if resume.source_path and os.path.exists(resume.source_path) else ""
    if not resume_path:
        raise ValueError("the selected résumé file is not available on disk")
    application = (
        store.get_application(target.get("application_job_id") or "")
        if target.get("application_job_id") else None
    )
    job = _followup_job(store, application, target["company"])
    followup = campaign.get("purpose") == "followup"
    generated_subject, generated_body = outreach.build_draft(
        cfg, store, resume, job,
        outreach.Target(
            email=email, source=contact.get("source") or "",
            confidence=contact.get("confidence") or "", domain=target.get("domain") or "",
            note=contact.get("note") or "",
        ),
        followup=followup,
        followup_kind="application" if application else "cold",
    )
    if followup and target.get("source_target_id"):
        source = store.get_outreach_campaign_target(target["source_target_id"])
        prior_subject = (source or {}).get("subject") or ""
        if prior_subject:
            generated_subject = (
                prior_subject if prior_subject.lower().startswith("re:")
                else f"Re: {prior_subject}"
            )
    return store.set_outreach_campaign_draft(
        target_id,
        selected_email=email,
        selected_source=contact.get("source") or "",
        selected_confidence=contact.get("confidence") or "",
        selected_note=contact.get("note") or "",
        subject=generated_subject if subject is None else subject,
        body=generated_body if body is None else body,
        resume_path=resume_path,
        domain=target.get("domain") or "",
        contacts=target.get("contacts") or [],
    )


def _application_keys(store) -> set[str]:
    return {
        normalize_company_key(application.get("company") or "")
        for application in store.applications(include_tombstoned=True)
        if normalize_company_key(application.get("company") or "")
    }


def _do_not_contact(cfg: dict, store, company: str, domain: str, email: str) -> bool:
    raw_blocked = {
        str(value).strip().lower()
        for value in (cfg.get("apply", {}).get("outreach", {}).get("do_not_contact") or [])
        if str(value).strip()
    }
    company_key = normalize_company_key(company)
    blocked_companies = {normalize_company_key(value) for value in raw_blocked}
    return (
        company.strip().lower() in raw_blocked
        or company_key in blocked_companies
        or domain.strip().lower() in raw_blocked
        or email.strip().lower() in raw_blocked
        or store.is_outreach_suppressed("company", company_key)
        or store.is_outreach_suppressed("domain", domain)
        or store.is_outreach_suppressed("email", email)
    )


def create_direct_intent(
    cfg: dict,
    store,
    *,
    company: str,
    recipient: str,
    subject: str,
    body: str,
    resume_path: str = "",
    application_job_id: str = "",
    contact_source: str = "override",
    contact_confidence: str = "high",
    contact_note: str = "user-selected direct outreach recipient",
) -> dict:
    """Persist one exact direct-outreach draft; never approve or send it."""
    email = (recipient or "").strip().lower()
    if not outreach.valid_recipient(email):
        raise ValueError("recipient must be valid and non-automated")
    domain = email.split("@", 1)[1]
    display_company = (company or domain).strip()
    company_key = normalize_company_key(display_company) or domain
    if _do_not_contact(cfg, store, display_company, domain, email):
        raise ValueError("recipient, domain, or company is suppressed")

    direct_key = application_job_id or company_key
    campaign = None
    target = None
    for candidate in store.outreach_campaigns():
        criteria = candidate.get("criteria") or {}
        if (criteria.get("direct_key") != direct_key
                or candidate.get("status") not in {"draft", "paused"}):
            continue
        targets = store.outreach_campaign_targets(candidate["id"])
        reusable = next((
            item for item in targets
            if item.get("state") not in {"sent", "replied", "opted_out"}
            and item.get("error_code") not in {"sending", "delivery_unknown"}
        ), None)
        if reusable is not None:
            campaign = candidate
            target = reusable
            break

    if campaign is None:
        defaults = _campaign_defaults(cfg)
        campaign = store.create_outreach_campaign(
            f"Direct outreach - {display_company}", 1, purpose="cold",
            criteria={"direct": True, "direct_key": direct_key},
            daily_limit=int(defaults.get("daily_limit", 2)),
            min_spacing_hours=float(defaults.get("min_spacing_hours", 4)),
            timezone=str(defaults.get("timezone", "Asia/Kolkata")),
            send_window_start=str(defaults.get("send_window_start", "10:00")),
            send_window_end=str(defaults.get("send_window_end", "17:00")),
        )
        target = store.upsert_outreach_campaign_target(
            campaign["id"], display_company, company_key,
            application_job_id=application_job_id, state="draft",
            evidence={"direct_intent": True},
        )

    contact = {
        "email": email,
        "source": contact_source,
        "confidence": contact_confidence,
        "note": contact_note,
    }
    store.set_outreach_campaign_contacts(
        target["id"], domain=domain, contacts=[contact], state="draft",
    )
    target = store.set_outreach_campaign_draft(
        target["id"], selected_email=email,
        selected_source=contact_source,
        selected_confidence=contact_confidence,
        selected_note=contact_note,
        subject=subject or "", body=body or "", resume_path=resume_path,
        domain=domain, contacts=[contact],
    )
    return {
        "ok": True,
        "sent": False,
        "queued": True,
        "campaign_id": campaign["id"],
        "target_id": target["id"],
        "target": target,
    }


def _permanent_guard(cfg: dict, store, target: dict) -> str:
    if target["company_key"] in _application_keys(store):
        return "application_history"
    if _do_not_contact(
        cfg, store, target["company"], target.get("domain") or "",
        target.get("selected_email") or "",
    ):
        return "do_not_contact"
    if not outreach.valid_company_recipient(
        target.get("selected_email") or "", target.get("domain") or "",
    ):
        return "invalid_recipient"
    if not target.get("resume_path") or not os.path.exists(target["resume_path"]):
        return "missing_resume"
    if not target.get("resume_sha256") or _file_sha256(target["resume_path"]) != target["resume_sha256"]:
        return "resume_changed"
    return ""


def _followup_guard(cfg: dict, store, target: dict, now: datetime) -> str:
    recipient = target.get("selected_email") or ""
    domain = target.get("domain") or ""
    if _do_not_contact(cfg, store, target["company"], domain, recipient):
        return "do_not_contact"
    if target.get("recipient_locked"):
        if not outreach.valid_recipient(recipient):
            return "invalid_recipient"
    elif not outreach.valid_company_recipient(recipient, domain):
        return "invalid_recipient"
    if not target.get("resume_path") or not os.path.exists(target["resume_path"]):
        return "missing_resume"
    if (not target.get("resume_sha256")
            or _file_sha256(target["resume_path"]) != target["resume_sha256"]):
        return "resume_changed"

    anchors: list[datetime] = []
    source_target_id = target.get("source_target_id") or ""
    if source_target_id:
        source = store.get_outreach_campaign_target(source_target_id)
        if source is None or source.get("state") != "sent" or not source.get("sent_at"):
            return "source_no_longer_pending"
        if recipient.lower() != (source.get("selected_email") or "").lower():
            return "recipient_changed"
        if (target.get("parent_message_id") or "") != (
            source.get("outbound_message_id") or ""
        ):
            return "thread_changed"
        source_at = _parse_iso(source["sent_at"])
        if source_at:
            anchors.append(source_at)

    application_job_id = target.get("application_job_id") or ""
    if application_job_id:
        application = store.get_application(application_job_id)
        if application is None or application.get("status") != "applied":
            return "application_no_longer_pending"
        application_at = _latest_timestamp(
            application.get("applied_at") or "", application.get("outreach_at") or "",
        )
        if application_at:
            anchors.append(application_at)
            if _has_response_after(store, application_job_id, application_at):
                return "application_has_response"
        original = application.get("outreach_to") or ""
        if original and target.get("recipient_locked") and recipient.lower() != original.lower():
            return "recipient_changed"

    if not anchors:
        return "followup_source_missing"
    days = int((cfg.get("apply", {}) or {}).get("followup_days", 7))
    if not _followup_is_due(max(anchors), days, _utc(now)):
        return "followup_not_due"
    return ""


def _next_schedule(campaign: dict, targets: list[dict], now: datetime) -> datetime:
    tz = _zone(campaign["timezone"])
    window_start = _clock(campaign["send_window_start"])
    window_end = _clock(campaign["send_window_end"])
    if window_start >= window_end:
        raise ValueError("campaign send window start must be before its end")
    spacing = timedelta(hours=float(campaign["min_spacing_hours"]))
    booked = [
        parsed for target in targets
        if (parsed := _parse_iso(target.get("sent_at") or target.get("scheduled_at") or ""))
    ]
    candidate = max([_utc(now), *[value + spacing for value in booked]])
    daily_limit = int(campaign["daily_limit"])
    for _ in range(370):
        local = candidate.astimezone(tz)
        start = datetime.combine(local.date(), window_start, tzinfo=tz)
        end = datetime.combine(local.date(), window_end, tzinfo=tz)
        if local < start:
            candidate = start.astimezone(timezone.utc)
            local = candidate.astimezone(tz)
        if local > end:
            next_day = local.date() + timedelta(days=1)
            candidate = datetime.combine(next_day, window_start, tzinfo=tz).astimezone(timezone.utc)
            continue
        on_day = sum(value.astimezone(tz).date() == local.date() for value in booked)
        if on_day >= daily_limit:
            next_day = local.date() + timedelta(days=1)
            candidate = datetime.combine(next_day, window_start, tzinfo=tz).astimezone(timezone.utc)
            continue
        return candidate
    raise RuntimeError("could not find an available campaign send slot")


def approve_target(
    cfg: dict, store, target_id: str, *, policy: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> dict:
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    normalized_policy = normalize_policy(policy or {}, target=target, campaign=campaign)
    target = store.set_outreach_campaign_policy(target_id, normalized_policy)
    error = (
        _followup_guard(cfg, store, target, _utc(now))
        if campaign.get("purpose") == "followup"
        else _permanent_guard(cfg, store, target)
    )
    if error:
        raise ValueError(error.replace("_", " "))
    scheduled = _next_schedule(
        campaign, store.outreach_campaign_targets(campaign["id"]), _utc(now),
    )
    store.approve_outreach_campaign_target(target_id)
    return store.schedule_outreach_campaign_target(target_id, _iso(scheduled))


def set_campaign_status(store, campaign_id: str, status: str) -> dict:
    if status == "active" and not any(
        _summary_state(target) == "approved"
        for target in store.outreach_campaign_targets(campaign_id)
    ):
        raise ValueError("approve at least one target before starting the campaign")
    store.set_outreach_campaign_status(campaign_id, status)
    return get_campaign_detail(store, campaign_id)


def activate_campaign(cfg: dict, store, campaign_id: str) -> dict:
    """Activate only after the exact approved MIME set passes SMTP preflight."""
    targets = [
        target for target in store.outreach_campaign_targets(campaign_id)
        if _summary_state(target) == "approved"
    ]
    if not targets:
        raise ValueError("approve at least one target before starting the campaign")

    readiness = sending_readiness(cfg, store)
    if not readiness["ok"]:
        raise ValueError("; ".join(readiness["errors"]))

    from jobscope.deliver import email
    largest_message_size = 0
    for target in targets:
        message = email.build_message(
            cfg, target["subject"], target["body"],
            to=target["selected_email"], attachments=[target["resume_path"]],
            message_id=_outbound_message_id(cfg, target),
            in_reply_to=target.get("parent_message_id") or "",
            references=target.get("root_message_id") or target.get("parent_message_id") or "",
        )
        largest_message_size = max(largest_message_size, len(message.as_bytes()))
    preflight = email.preflight(cfg, message_size=largest_message_size)
    if not preflight.get("ok"):
        raise ValueError(f"SMTP preflight failed: {preflight.get('code') or 'unknown'}")
    return set_campaign_status(store, campaign_id, "active")


def _local_day_bounds(campaign: dict, now: datetime) -> tuple[str, str, date]:
    tz = _zone(campaign["timezone"])
    local_day = now.astimezone(tz).date()
    start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    return _iso(start), _iso(end), local_day


def _inside_window(campaign: dict, now: datetime) -> bool:
    local_time = now.astimezone(_zone(campaign["timezone"])).time().replace(tzinfo=None)
    return _clock(campaign["send_window_start"]) <= local_time <= _clock(campaign["send_window_end"])


def _within_days(value: str, days: float, now: datetime) -> bool:
    parsed = _parse_iso(value)
    return bool(parsed and now - parsed < timedelta(days=max(0, days)))


def _outbound_message_id(cfg: dict, target: dict) -> str:
    sender = str(cfg.get("email", {}).get("from_addr") or "")
    sender_domain = sender.split("@", 1)[1].lower() if "@" in sender else "localhost"
    digest = hashlib.sha256(
        f"{target['id']}\0{target.get('approval_hash') or ''}".encode("utf-8")
    ).hexdigest()[:24]
    return f"jobscope-campaign-{digest}@{sender_domain}"


def send_target(cfg: dict, store, target_id: str, *, now: Optional[datetime] = None,
                ignore_schedule: bool = False, allow_inactive: bool = False) -> dict:
    current = _utc(now)
    store.mark_stale_outreach_campaign_sends_unknown(
        _iso(current - _STALE_SEND_CLAIM),
    )
    blocker = store.outreach_campaign_delivery_blocker()
    if blocker:
        code = {
            "delivery_unknown": "delivery_unknown",
            "transient_bounce": "provider_feedback_review_required",
        }.get(blocker, "send_in_progress")
        return {
            "ok": False, "sent": False,
            "code": code,
        }
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    if campaign["status"] != "active" and not (
        allow_inactive and campaign["status"] in {"draft", "paused"}
    ):
        return {"ok": False, "sent": False, "code": "campaign_inactive"}
    if target.get("error_code") == "delivery_unknown":
        return {"ok": False, "sent": False, "code": "delivery_unknown"}
    if target.get("error_code") == "sending":
        return {"ok": False, "sent": False, "code": "send_in_progress"}
    try:
        normalized_policy = normalize_policy(
            target.get("policy") or {}, target=target, campaign=campaign,
        )
    except ValueError:
        return {"ok": False, "sent": False, "code": "policy_review_required"}
    if normalized_policy != (target.get("policy") or {}):
        return {"ok": False, "sent": False, "code": "policy_review_required"}
    if target["state"] != "approved" or not store.outreach_campaign_approval_valid(target_id):
        return {"ok": False, "sent": False, "code": "approval_required"}
    scheduled = _parse_iso(target.get("scheduled_at") or "")
    if not ignore_schedule and (scheduled is None or scheduled > current):
        return {"ok": False, "sent": False, "code": "not_due"}

    permanent = (
        _followup_guard(cfg, store, target, current)
        if campaign.get("purpose") == "followup"
        else _permanent_guard(cfg, store, target)
    )
    if permanent:
        if permanent == "followup_not_due":
            return {"ok": False, "sent": False, "code": permanent}
        state = "skipped" if permanent in {
            "application_history", "do_not_contact", "invalid_recipient",
            "application_no_longer_pending", "application_has_response",
            "source_no_longer_pending", "recipient_changed", "thread_changed",
        } else "failed"
        store.set_outreach_campaign_target_state(
            target_id, state, error_code=permanent,
            error_detail=permanent.replace("_", " "),
        )
        return {"ok": False, "sent": False, "code": permanent}
    if not _inside_window(campaign, current):
        return {"ok": False, "sent": False, "code": "outside_send_window"}

    start, end, _ = _local_day_bounds(campaign, current)
    sent_today = store.sent_outreach_campaign_targets(start_at=start, end_at=end)
    if len(sent_today) >= min(int(campaign["daily_limit"]), MAX_CAMPAIGN_DAILY_LIMIT):
        return {"ok": False, "sent": False, "code": "daily_limit"}
    last_sent = store.last_outreach_campaign_sent_at()
    if last_sent and _within_days(
        last_sent, float(campaign["min_spacing_hours"]) / 24, current,
    ):
        return {"ok": False, "sent": False, "code": "minimum_spacing"}
    if campaign.get("purpose") != "followup":
        cooldown_days = int(cfg.get("apply", {}).get("outreach", {}).get("cooldown_days", 14))
        previous = store.last_outreach_campaign_sent_at(target["company_key"])
        if previous and _within_days(previous, cooldown_days, current):
            store.set_outreach_campaign_target_state(
                target_id, "skipped", error_code="company_cooldown",
                error_detail="company was contacted within the cooldown window",
            )
            return {"ok": False, "sent": False, "code": "company_cooldown"}
    outreach_cfg = cfg.get("apply", {}).get("outreach", {}) or {}
    if not outreach_cfg.get("enabled") or not cfg.get("email", {}).get("enabled"):
        return {"ok": False, "sent": False, "code": "sending_disabled"}
    message_id = _outbound_message_id(cfg, target)
    approval_hash = str(target.get("approval_hash") or "")
    if not store.claim_outreach_campaign_target_send(
        target_id, message_id, expected_approval_hash=approval_hash,
    ):
        refreshed = store.get_outreach_campaign_target(target_id) or {}
        refreshed_guard = (
            _followup_guard(cfg, store, refreshed, current)
            if campaign.get("purpose") == "followup" else _permanent_guard(cfg, store, refreshed)
        )
        return {
            "ok": False, "sent": False,
            "code": refreshed_guard or "approval_or_claim_invalid",
        }

    try:
        from jobscope.deliver import email
        sent = email.send(
            cfg, target["subject"], target["body"], to=target["selected_email"],
            attachments=[target["resume_path"]], message_id=message_id,
            in_reply_to=target.get("parent_message_id") or "",
            references=target.get("root_message_id") or target.get("parent_message_id") or "",
            raise_errors=True,
        )
    except email.EmailDeliveryError as exc:
        if exc.outcome_unknown:
            store.mark_outreach_campaign_delivery_unknown(target_id, str(exc))
            return {"ok": False, "sent": False, "code": "delivery_unknown"}
        error_code = {
            "pre_send_failure": "smtp_pre_send_failure",
            "transient_rejection": "smtp_transient_rejection",
            "permanent_rejection": "smtp_permanent_rejection",
        }.get(exc.outcome, "smtp_failed")
        store.set_outreach_campaign_target_state(
            target_id, "failed", error_code=error_code, error_detail=str(exc),
        )
        return {"ok": False, "sent": False, "code": error_code}
    if not sent:
        store.set_outreach_campaign_target_state(
            target_id, "failed", error_code="smtp_failed", error_detail="SMTP send failed",
        )
        return {"ok": False, "sent": False, "code": "smtp_failed"}
    stored = store.mark_outreach_campaign_target_sent(target_id, _iso(current))
    return {"ok": True, "sent": True, "target": stored}


def send_next_approved(cfg: dict, store, *, campaign_id: str = "",
                       now: Optional[datetime] = None) -> dict:
    current = _utc(now)
    store.mark_stale_outreach_campaign_sends_unknown(
        _iso(current - _STALE_SEND_CLAIM),
    )
    blocker = store.outreach_campaign_delivery_blocker()
    if blocker:
        code = {
            "delivery_unknown": "delivery_unknown",
            "transient_bounce": "provider_feedback_review_required",
        }.get(blocker, "send_in_progress")
        return {
            "ok": False, "sent": False,
            "code": code,
        }
    due = store.due_outreach_campaign_targets(_iso(current), campaign_id=campaign_id)
    if not due:
        return {"ok": True, "sent": False, "code": "nothing_due"}
    return send_target(cfg, store, due[0]["id"], now=current)


def resolve_delivery(store, target_id: str, outcome: str) -> dict:
    return store.resolve_outreach_campaign_delivery(target_id, outcome)


def reconcile_delivery(cfg: dict, store, target_id: str) -> dict:
    """Resolve an unknown campaign send using exact read-only Sent evidence."""
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    if target.get("error_code") != "delivery_unknown":
        raise ValueError("target is not awaiting delivery resolution")
    message_id = str(target.get("outbound_message_id") or "").strip().strip("<>")
    if not message_id:
        return {"ok": False, "code": "missing_message_id"}

    from jobscope.ingest import inbox
    evidence = inbox.find_sent_message(cfg, message_id)
    if not evidence.get("ok"):
        return {
            "ok": False, "code": evidence.get("code") or "sent_reconciliation_failed",
        }
    status = str(evidence.get("status") or "")
    count = int(evidence.get("count") or 0)
    if status == "multiple":
        return {
            "ok": False, "code": "multiple_sent_matches",
            "status": status, "count": count,
        }
    if status not in {"sent", "not_found"}:
        return {"ok": False, "code": "invalid_sent_evidence"}
    resolved = store.resolve_outreach_campaign_delivery(
        target_id, "sent" if status == "sent" else "not_sent",
    )
    return {
        "ok": True, "code": status, "status": status,
        "count": count, "target": resolved,
    }


def resolve_feedback(store, target_id: str, outcome: str) -> dict:
    return store.resolve_outreach_campaign_transient_bounce(target_id, outcome)


def export_target_eml(cfg: dict, store, target_id: str, path: str = "") -> dict:
    """Export the exact saved target as MIME without approval, SMTP, inbox, or AI."""
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    if not target.get("selected_email") or not target.get("subject") or not target.get("body"):
        raise ValueError("recipient, subject, and body are required for EML export")
    resume = _resume_for_campaign(store, campaign)
    sender = str(cfg.get("email", {}).get("from_addr") or "").strip()
    sender = sender or str(getattr(resume, "email", "") or "").strip()
    if not sender:
        raise ValueError("sender address is required for EML export")
    if not path:
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", target_id).strip("-")
        path = os.path.join("data", "outreach-eml", f"{filename}.eml")
    attachments = [target["resume_path"]] if target.get("resume_path") else None
    message_id = (
        target.get("outbound_message_id") or
        (_outbound_message_id(cfg, target) if target.get("approval_hash") else "")
    )
    from jobscope.deliver import email
    destination = email.write_eml(
        cfg, path, target["subject"], target["body"],
        to=target["selected_email"], from_addr=sender,
        attachments=attachments, message_id=message_id,
        in_reply_to=target.get("parent_message_id") or "",
        references=target.get("root_message_id") or target.get("parent_message_id") or "",
    )
    return {"ok": True, "path": destination, "target_id": target_id}


_REPLY_SIGNALS = {"recruiter", "assessment", "interview", "offer"}
_FEEDBACK_SIGNALS = {
    "campaign_hard_bounce": "hard_bounce",
    "campaign_transient_bounce": "transient_bounce",
    "campaign_complaint": "complaint",
}
_OUTBOUND_ID_RE = re.compile(
    r"jobscope-campaign-[0-9a-f]{24}@[A-Za-z0-9.-]+",
    re.IGNORECASE,
)
_OPTOUT_PHRASES = (
    "do not contact", "don't contact", "remove me", "stop emailing", "unsubscribe",
    "opt out", "opt-out",
)


def _provider_feedback_kind(event: dict) -> str:
    explicit = _FEEDBACK_SIGNALS.get(str(event.get("signal") or ""))
    if explicit:
        return explicit
    text = f"{event.get('subject') or ''} {event.get('snippet') or ''}".casefold()
    if any(value in text for value in (
        "abuse complaint", "spam complaint", "feedback report", "reported as spam",
    )):
        return "complaint"
    if any(value in text for value in (
        "status: 5.", "permanent failure", "user unknown", "mailbox not found",
        "recipient address rejected", "undeliverable",
    )):
        return "hard_bounce"
    if any(value in text for value in (
        "status: 4.", "temporary failure", "delivery delayed", "mailbox full",
        "try again later",
    )):
        return "transient_bounce"
    return ""


def _provider_feedback_message_id(event: dict) -> str:
    thread_id = str(event.get("thread_id") or "").strip().strip("<>")
    if _OUTBOUND_ID_RE.fullmatch(thread_id):
        return thread_id
    text = f"{event.get('subject') or ''}\n{event.get('snippet') or ''}"
    match = _OUTBOUND_ID_RE.search(text)
    return match.group(0) if match else ""


def classify_provider_feedback(
    subject: str, body: str, thread_id: str, known_message_ids: set[str],
) -> tuple[str, str]:
    """Return a campaign feedback signal and exact known outbound Message-ID."""
    event = {
        "signal": "other",
        "subject": subject,
        "snippet": body,
        "thread_id": thread_id,
    }
    kind = _provider_feedback_kind(event)
    message_id = _provider_feedback_message_id(event)
    normalized_known = {
        str(value).strip().strip("<>") for value in known_message_ids if value
    }
    if not kind or message_id not in normalized_known:
        return "", ""
    signal = {
        "hard_bounce": "campaign_hard_bounce",
        "transient_bounce": "campaign_transient_bounce",
        "complaint": "campaign_complaint",
    }[kind]
    return signal, message_id


def reconcile_provider_feedback(store) -> dict:
    """Apply DSNs and complaints once, correlated by stable outbound Message-ID."""
    stats = {
        "hard_bounce": 0,
        "transient_bounce": 0,
        "complaint": 0,
        "duplicate": 0,
        "ambiguous": 0,
    }
    for event in store.mail_events():
        kind = _provider_feedback_kind(event)
        if not kind:
            continue
        message_id = _provider_feedback_message_id(event)
        target = store.outreach_campaign_target_by_message_id(message_id)
        event_id = str(event.get("id") or "")
        event_at = _parse_iso(event.get("date") or event.get("first_seen") or "")
        sent_at = _parse_iso((target or {}).get("sent_at") or "")
        if (not target or not event_id or event_at is None or sent_at is None
                or event_at <= sent_at):
            stats["ambiguous"] += 1
            continue
        applied, _updated = store.apply_outreach_campaign_feedback(
            target["id"], event_id, kind, _iso(event_at),
        )
        stats[kind if applied else "duplicate"] += 1
    return stats


def is_optout_text(subject: str, body: str = "") -> bool:
    content = f"{subject or ''} {body or ''}".casefold()
    return any(phrase in content for phrase in _OPTOUT_PHRASES)


def _reply_event_kind(event: dict) -> str:
    is_optout = event.get("signal") == "campaign_optout" or is_optout_text(
        event.get("subject") or "", event.get("snippet") or "",
    )
    if is_optout and event.get("signal") in {"other", "campaign_optout"}:
        return "optout"
    if event.get("signal") in (_REPLY_SIGNALS | {"campaign_reply"}):
        return "optout" if is_optout else "reply"
    return ""


def _find_reply_event(
    target: dict, events: list[dict], used_event_ids: set[str], *,
    exact_only: bool, known_message_ids: set[str],
) -> tuple[dict, str] | None:
    sent_at = _parse_iso(target.get("sent_at") or "")
    if sent_at is None:
        return None
    outbound_id = target.get("outbound_message_id") or ""
    for event in sorted(
        events, key=lambda value: value.get("date") or value.get("first_seen") or "",
    ):
        event_id = str(event.get("id") or "")
        if not event_id or event_id in used_event_ids:
            continue
        thread_id = str(event.get("thread_id") or "")
        if exact_only:
            if not outbound_id or thread_id != outbound_id:
                continue
        elif thread_id in known_message_ids:
            continue
        event_at = _parse_iso(event.get("date") or event.get("first_seen") or "")
        if event_at is None or event_at <= sent_at:
            continue
        address = str(event.get("from_addr") or "").strip().lower()
        if not outreach.valid_company_recipient(address, target.get("domain") or ""):
            continue
        kind = _reply_event_kind(event)
        if kind:
            return event, kind
    return None


def _apply_reply_event(store, target: dict, event: dict, kind: str) -> None:
    event_at = _parse_iso(event.get("date") or event.get("first_seen") or "")
    if event_at is None:
        return
    address = str(event.get("from_addr") or "").strip().lower()
    opted_out = kind == "optout"
    if opted_out:
        store.add_outreach_suppression(
            "email", address, reason="recipient opt-out", source=event.get("id") or "",
        )
        store.add_outreach_suppression(
            "domain", target["domain"], reason="recipient opt-out",
            source=event.get("id") or "",
        )
    store.mark_outreach_campaign_target_reply(
        target["id"], _iso(event_at), event_id=event.get("id") or "",
        opted_out=opted_out,
    )


def reconcile_replies(store) -> dict:
    """Link each inbound event once; prefer exact thread over unambiguous domain fallback."""
    events = store.mail_events()
    replied = opted_out = 0
    all_targets = store.sent_outreach_campaign_targets()
    pending = [target for target in all_targets if target["state"] == "sent"]
    used_event_ids = {
        str(target.get("reply_event_id") or "") for target in all_targets
        if target.get("reply_event_id")
    }
    known_message_ids = {
        str(target.get("outbound_message_id") or "") for target in all_targets
        if target.get("outbound_message_id")
    }

    for target in list(pending):
        found = _find_reply_event(
            target, events, used_event_ids, exact_only=True,
            known_message_ids=known_message_ids,
        )
        if found is None:
            continue
        event, kind = found
        _apply_reply_event(store, target, event, kind)
        used_event_ids.add(event["id"])
        pending.remove(target)
        replied += kind == "reply"
        opted_out += kind == "optout"

    domains: dict[str, list[dict]] = {}
    for target in pending:
        domains.setdefault(str(target.get("domain") or "").lower(), []).append(target)
    for targets in domains.values():
        if len(targets) != 1:
            continue
        target = targets[0]
        found = _find_reply_event(
            target, events, used_event_ids, exact_only=False,
            known_message_ids=known_message_ids,
        )
        if found is None:
            continue
        event, kind = found
        _apply_reply_event(store, target, event, kind)
        used_event_ids.add(event["id"])
        replied += kind == "reply"
        opted_out += kind == "optout"
    return {"replied": replied, "opted_out": opted_out}


def sync_replies(cfg: dict, store, *, fetch: bool = True) -> dict:
    """Incrementally sync configured inboxes, then reconcile campaign replies."""
    pending = sum(
        target["state"] == "sent" for target in store.sent_outreach_campaign_targets()
    )
    inbox_status = "not_needed" if not pending else "not_fetched"
    inbox_code = 0
    error = ""
    if fetch and pending:
        inbox_cfg = cfg.get("inbox", {}) or {}
        if not inbox_cfg.get("enabled"):
            inbox_status = "disabled"
        elif not inbox_cfg.get("accounts"):
            inbox_status = "unconfigured"
        else:
            try:
                from jobscope.ingest import inbox
                inbox_code = inbox.run(cfg, store, initiator="local_refresh")
                inbox_status = "ok" if inbox_code == 0 else "error"
            except Exception as exc:  # noqa: BLE001 - preserve local history on IMAP failure
                inbox_code = 1
                inbox_status = "error"
                error = str(exc)[:200]
    feedback = reconcile_provider_feedback(store)
    stats = reconcile_replies(store)
    checked_at = _iso(_utc())
    store.meta_set("campaign:replies:last_checked_at", checked_at)
    store.meta_set("campaign:replies:last_status", inbox_status)
    return {
        "ok": inbox_code == 0,
        "checked_at": checked_at,
        "inbox_status": inbox_status,
        "pending": pending,
        "replied": stats["replied"],
        "opted_out": stats["opted_out"],
        "feedback": feedback,
        "error": error,
    }


def tick(cfg: dict, store, *, campaign_id: str = "",
         now: Optional[datetime] = None) -> dict:
    """Reconcile replies and report due work without sending email."""
    tracking = sync_replies(cfg, store, fetch=True)
    due = store.due_outreach_campaign_targets(
        _iso(_utc(now)), campaign_id=campaign_id,
    )
    sync_required = bool(
        tracking.get("pending")
        and tracking.get("inbox_status") != "ok"
    )
    code = "reply_sync_required" if sync_required else "reconciliation_only"
    delivery = {
        "ok": not sync_required,
        "sent": False,
        "code": code,
        "due_count": len(due),
    }
    return {
        "ok": not sync_required,
        "tracking": tracking,
        "delivery": delivery,
        "sent": False,
        "code": code,
    }