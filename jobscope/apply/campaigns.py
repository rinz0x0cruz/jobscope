"""Local-only, individually approved recruiter outreach campaigns."""
from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jobscope.apply import outreach
from jobscope.apply.company_rank import is_security_role, rank_companies
from jobscope.core.model import Job
from jobscope.core.store.monitoring import normalize_company_key
from jobscope.core.store.outreach_campaigns import MAX_CAMPAIGN_DAILY_LIMIT


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


def get_campaign_detail(store, campaign_id: str) -> dict:
    campaign = store.get_outreach_campaign(campaign_id)
    if campaign is None:
        raise KeyError(campaign_id)
    targets = store.outreach_campaign_targets(campaign_id)
    counts: dict[str, int] = {}
    for target in targets:
        counts[target["state"]] = counts.get(target["state"], 0) + 1
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
            counts[target["state"]] = counts.get(target["state"], 0) + 1
        delivered = sum(counts.get(state, 0) for state in ("sent", "replied", "opted_out"))
        responses = sum(counts.get(state, 0) for state in ("replied", "opted_out"))
        result.append({
            **campaign, "counts": counts, "target_count": len(targets),
            "delivered_count": delivered, "response_count": responses,
        })
    return result


def sending_readiness(cfg: dict) -> dict:
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
    candidates = [
        target for target in store.outreach_campaign_targets(campaign_id)
        if target["state"] == "ranked"
    ][:limit]
    drafted = needs_contact = failed = 0
    for target in candidates:
        try:
            result = discover_target(cfg, store, target["id"], fetch=fetch)
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
    contact = next(
        (item for item in target.get("contacts") or []
         if str(item.get("email") or "").strip().lower() == email),
        None,
    )
    if contact is None:
        raise ValueError("select one of the discovered contacts")
    if not outreach.valid_company_recipient(email, target.get("domain") or ""):
        raise ValueError("recipient must be valid, non-automated, and on the company domain")
    resume = _resume_for_campaign(store, campaign)
    if resume is None:
        raise ValueError("upload or select a résumé before drafting campaign outreach")
    resume_path = resume.source_path if resume.source_path and os.path.exists(resume.source_path) else ""
    if not resume_path:
        raise ValueError("the selected résumé file is not available on disk")
    job = _representative_job(store, target["company"])
    generated_subject, generated_body = outreach.build_draft(
        cfg, store, resume, job,
        outreach.Target(
            email=email, source=contact.get("source") or "",
            confidence=contact.get("confidence") or "", domain=target.get("domain") or "",
            note=contact.get("note") or "",
        ),
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


def approve_target(cfg: dict, store, target_id: str, *, now: Optional[datetime] = None) -> dict:
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    error = _permanent_guard(cfg, store, target)
    if error:
        raise ValueError(error.replace("_", " "))
    campaign = store.get_outreach_campaign(target["campaign_id"])
    scheduled = _next_schedule(
        campaign, store.outreach_campaign_targets(campaign["id"]), _utc(now),
    )
    store.approve_outreach_campaign_target(target_id)
    return store.schedule_outreach_campaign_target(target_id, _iso(scheduled))


def set_campaign_status(store, campaign_id: str, status: str) -> dict:
    if status == "active" and not any(
        target["state"] == "approved"
        for target in store.outreach_campaign_targets(campaign_id)
    ):
        raise ValueError("approve at least one target before starting the campaign")
    store.set_outreach_campaign_status(campaign_id, status)
    return get_campaign_detail(store, campaign_id)


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
                ignore_schedule: bool = False) -> dict:
    current = _utc(now)
    target = store.get_outreach_campaign_target(target_id)
    if target is None:
        raise KeyError(target_id)
    campaign = store.get_outreach_campaign(target["campaign_id"])
    if campaign is None:
        raise KeyError(target["campaign_id"])
    if campaign["status"] != "active":
        return {"ok": False, "sent": False, "code": "campaign_inactive"}
    if target.get("error_code") == "delivery_unknown":
        return {"ok": False, "sent": False, "code": "delivery_unknown"}
    if target.get("error_code") == "sending":
        return {"ok": False, "sent": False, "code": "send_in_progress"}
    if target["state"] != "approved" or not store.outreach_campaign_approval_valid(target_id):
        return {"ok": False, "sent": False, "code": "approval_required"}
    scheduled = _parse_iso(target.get("scheduled_at") or "")
    if not ignore_schedule and (scheduled is None or scheduled > current):
        return {"ok": False, "sent": False, "code": "not_due"}

    permanent = _permanent_guard(cfg, store, target)
    if permanent:
        state = "skipped" if permanent in {
            "application_history", "do_not_contact", "invalid_recipient",
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
    if not store.claim_outreach_campaign_target_send(target_id, message_id):
        return {"ok": False, "sent": False, "code": "send_in_progress"}

    try:
        from jobscope.deliver import email
        sent = email.send(
            cfg, target["subject"], target["body"], to=target["selected_email"],
            attachments=[target["resume_path"]], message_id=message_id,
            raise_errors=True,
        )
    except email.EmailDeliveryError as exc:
        if exc.outcome_unknown:
            store.mark_outreach_campaign_delivery_unknown(target_id, str(exc))
            return {"ok": False, "sent": False, "code": "delivery_unknown"}
        store.set_outreach_campaign_target_state(
            target_id, "failed", error_code="smtp_failed", error_detail=str(exc),
        )
        return {"ok": False, "sent": False, "code": "smtp_failed"}
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
    due = store.due_outreach_campaign_targets(_iso(current), campaign_id=campaign_id)
    if not due:
        return {"ok": True, "sent": False, "code": "nothing_due"}
    return send_target(cfg, store, due[0]["id"], now=current)


def resolve_delivery(store, target_id: str, outcome: str) -> dict:
    return store.resolve_outreach_campaign_delivery(target_id, outcome)


_REPLY_SIGNALS = {"recruiter", "assessment", "interview", "offer"}
_OPTOUT_PHRASES = (
    "do not contact", "don't contact", "remove me", "stop emailing", "unsubscribe",
    "opt out", "opt-out",
)


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
        "error": error,
    }


def tick(cfg: dict, store, *, campaign_id: str = "",
         now: Optional[datetime] = None) -> dict:
    """One scheduler tick: reconcile replies, then send at most one due email."""
    tracking = sync_replies(cfg, store, fetch=True)
    delivery = send_next_approved(cfg, store, campaign_id=campaign_id, now=now)
    return {
        "ok": bool(delivery.get("ok")),
        "tracking": tracking,
        "delivery": delivery,
        "sent": bool(delivery.get("sent")),
        "code": delivery.get("code") or "",
    }