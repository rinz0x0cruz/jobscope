"""Sync Gmail inboxes (read-only IMAP) for job-application-status emails.

This is the automated inbound side of the application funnel: it reads the
mailboxes you configure, deterministically classifies each message with
:mod:`jobscope.mailrules`, records the relevant ones as ``mail_events``, and
advances the matching application's status. It is the I/O half of the feature --
all judgement lives in the pure ``mailrules`` module.

Design notes:
* **Read-only.** The mailbox is opened ``readonly=True`` and every fetch uses
  ``BODY.PEEK`` so messages are never marked read and nothing is ever mutated.
* **Incremental.** A per-account UID watermark (in ``meta``) means normal runs
  only look at new mail; the first run (or ``--backfill``) scans ``lookback_days``.
* **Best-effort.** One malformed message never sinks a run (per-message
  try/except), mirroring ``scrape.py``.
* **Credentials via env only.** App passwords are read from the environment
  variable named in config; nothing sensitive is stored on disk by jobscope.
* **AI optional.** When weighted scoring leaves two or more signals in a
  close-call tie, the gated AI/quorum layer may arbitrate among the tied
  labels only; classification never requires it and degrades deterministically.
"""
from __future__ import annotations

import datetime as _dt
import email as _email
import email.utils as _eu
import hashlib
import imaplib
import re
import time
from dataclasses import dataclass
from email.header import decode_header, make_header
from typing import Optional

from .ats import _strip_html
from jobscope.core.config import inbox_password
from jobscope.core.model import Application, MailEvent
from jobscope.core.store import now_iso
from . import mailrules

_HEADER_FIELDS = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO)])"


class _TransientIMAPError(RuntimeError):
    pass


class _InboxStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _AccountSyncResult:
    count: int
    ok: bool


def _purge_reconciliation_audit(cfg: dict, store) -> int:
    days = int((cfg.get("retention", {}) or {}).get(
        "reconciliation_audit_days", 730,
    ) or 0)
    return store.purge_reconciliation_decisions(days) if days > 0 else 0


def run(cfg: dict, store, *, dry_run: bool = False, account: Optional[str] = None,
        since: Optional[str] = None, backfill: bool = False,
    reclassify: bool = False, initiator: str = "cli") -> int:
    if reclassify:
        # Offline repair: re-check stored events against the current rules and
        # rebuild the funnel (instance-split), without touching Gmail.
        from . import reconcile
        stats = reconcile.reclassify(store, initiator=initiator)
        purged = _purge_reconciliation_audit(cfg, store)
        print(f"  reclassified {stats['reclassified']} event(s), dropped "
              f"{stats['dropped']} transactional, rebuilt {stats['instances']} "
              f"application instance(s) across {stats['groups']} thread(s).")
        if purged:
            print(f"  purged {purged} expired reconciliation decision(s).")
        return 0
    icfg = cfg.get("inbox", {}) or {}
    if not icfg.get("enabled"):
        print("  inbox is disabled. Set inbox.enabled: true and add accounts in config.yaml,")
        print("  then put each Gmail app password in .env (see inbox.accounts[].password_env).")
        return 0
    accounts = icfg.get("accounts") or []
    if account:
        accounts = [a for a in accounts if a.get("email") == account]
    if not accounts:
        print("  no matching inbox accounts configured.")
        return 0

    total_new = 0
    failed_accounts = 0
    for acct in accounts:
        result = _sync_account(
            cfg, store, acct, dry_run=dry_run, since=since, backfill=backfill)
        total_new += result.count
        failed_accounts += not result.ok

    if not dry_run:
        # Rebuild the funnel from the timeline so a rejection for one application
        # never collapses a company that has other (or later) active applications.
        from . import reconcile
        reconcile.recompute(store, initiator=initiator)
        _purge_reconciliation_audit(cfg, store)

    verb = "would ingest" if dry_run else "ingested"
    print(f"\n  inbox: {verb} {total_new} job-related email(s) across "
          f"{len(accounts)} account(s).")
    if total_new and not dry_run:
        print("  next: python -m jobscope track   |   python -m jobscope dashboard --open")
    return 1 if failed_accounts else 0


def _folders_for(icfg: dict) -> list[str]:
    """Folders to scan per account: the configured folder (default INBOX), plus
    Gmail's spam folder when ``inbox.include_spam`` is set -- so a real
    application email Gmail misfiled as spam is still picked up."""
    folders = [icfg.get("folder", "INBOX")]
    if icfg.get("include_spam"):
        spam = icfg.get("spam_folder", "[Gmail]/Spam")
        if spam and spam not in folders:
            folders.append(spam)
    return [f for f in folders if f]


def _uid_marker(addr: str, folder: str) -> str:
    """Incremental UID watermark key, per account+folder. INBOX keeps the legacy
    key so existing watermarks stay valid (no surprise full rescan on upgrade)."""
    return f"inbox:{addr}:last_uid" if folder == "INBOX" else f"inbox:{addr}:{folder}:last_uid"


def _uidvalidity_marker(addr: str, folder: str) -> str:
    suffix = "uidvalidity" if folder == "INBOX" else f"{folder}:uidvalidity"
    return f"inbox:{addr}:{suffix}"


def _response_number(M, name: str) -> int | None:
    try:
        _typ, data = M.response(name)
    except imaplib.IMAP4.abort:
        raise
    except OSError as exc:
        raise _TransientIMAPError(f"IMAP {name} response failed: {exc}") from exc
    except (AttributeError, imaplib.IMAP4.error):
        return None
    if not data:
        return None
    raw = b" ".join(
        item if isinstance(item, bytes) else str(item).encode("ascii", errors="ignore")
        for item in data if item is not None
    )
    match = re.search(rb"\d+", raw)
    return int(match.group()) if match else None


def _sync_account(cfg: dict, store, acct: dict, *, dry_run: bool, since: Optional[str],
                  backfill: bool) -> _AccountSyncResult:
    icfg = cfg["inbox"]
    addr = (acct.get("email") or "").strip()
    pw = inbox_password(cfg, acct)
    if not addr or not pw:
        env = acct.get("password_env", "?")
        print(f"  [skip] {addr or '(no email)'}: missing app password "
              f"(set env {env} in .env)")
        source = f"inbox:{addr or '(missing account)'}"
        store.log_run(source, 0, "error")
        store.set_source_health(
            source, provider="imap", slug=addr, status="error",
            detail=f"missing app password reference {env}",
        )
        return _AccountSyncResult(0, False)

    host = icfg.get("imap_host", "imap.gmail.com")
    port = int(icfg.get("imap_port", 993))
    lookback_days = int(acct.get("lookback_days", icfg.get("lookback_days", 90)))
    attempts = max(1, int(icfg.get("imap_attempts", 3)))

    # Prebuild a company -> job-id index once so email->job linking is O(1)/email.
    job_index: dict[str, str] = {}
    for j in store.jobs(order_by_score=False):
        if j.company:
            job_index.setdefault(mailrules.normalize_company(j.company), j.id)
    campaign_reply_watches = [
        {
            "domain": target.get("domain") or "",
            "sent_at": target.get("sent_at") or "",
            "outbound_message_id": target.get("outbound_message_id") or "",
        }
        for target in store.sent_outreach_campaign_targets()
        if target.get("state") == "sent" and target.get("domain") and target.get("sent_at")
    ]

    track_new_ids = not (dry_run or backfill)
    initial_event_ids = {
        event["id"] for event in store.mail_events()
        if event.get("account") == addr
    } if track_new_ids else set()

    for attempt in range(1, attempts + 1):
        M = None
        try:
            M = imaplib.IMAP4_SSL(host, port)
            M.login(addr, pw)
            kept = 0
            for folder in _folders_for(icfg):
                kept += _sync_folder(M, addr, folder, store, cfg, job_index,
                                     campaign_reply_watches,
                                     dry_run=dry_run, since=since, backfill=backfill,
                                     lookback_days=lookback_days)
            status = "recovered" if attempt > 1 else "ok"
            store.set_source_health(
                f"inbox:{addr}", provider="imap", slug=addr, status=status,
                item_count=kept, attempts=attempt,
            )
            if track_new_ids:
                current_ids = {
                    event["id"] for event in store.mail_events()
                    if event.get("account") == addr
                }
                return _AccountSyncResult(len(current_ids - initial_event_ids), True)
            return _AccountSyncResult(kept, True)
        except (imaplib.IMAP4.abort, _TransientIMAPError) as exc:
            if attempt < attempts:
                print(f"  [retry] {addr}: IMAP session aborted ({exc}); "
                      f"reconnecting ({attempt + 1}/{attempts})")
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 2.0))
                continue
            detail = f"IMAP session aborted after {attempts} attempt(s): {exc}"
        except OSError as exc:
            if attempt < attempts:
                print(f"  [retry] {addr}: cannot reach {host}:{port} ({exc}); "
                      f"reconnecting ({attempt + 1}/{attempts})")
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 2.0))
                continue
            detail = f"cannot reach {host}:{port} after {attempts} attempt(s): {exc}"
        except imaplib.IMAP4.error as exc:
            detail = (f"IMAP login failed: {exc}. Check the app password and "
                      "that IMAP is enabled.")
        except _InboxStateError as exc:
            detail = str(exc)
        finally:
            if M is not None:
                try:
                    M.logout()
                except Exception:  # noqa: BLE001
                    pass

        print(f"  [skip] {addr}: {detail}")
        store.log_run(f"inbox:{addr}", 0, "error")
        store.set_source_health(
            f"inbox:{addr}", provider="imap", slug=addr, status="error",
            attempts=attempt, detail=detail,
        )
        return _AccountSyncResult(0, False)
    return _AccountSyncResult(0, False)


def _sync_folder(M, addr: str, folder: str, store, cfg: dict, job_index: dict,
                 campaign_reply_watches: list[dict], *,
                 dry_run: bool, since: Optional[str], backfill: bool,
                 lookback_days: int) -> int:
    """Scan a single IMAP folder for one account; returns the newly-ingested count.
    A missing folder (e.g. no localized Spam) is skipped quietly."""
    marker = _uid_marker(addr, folder)
    validity_marker = _uidvalidity_marker(addr, folder)
    stored_last_uid = int(store.meta_get(marker, "0") or 0)
    try:
        typ, _ = M.select(folder, readonly=True)
    except imaplib.IMAP4.abort:
        raise
    except imaplib.IMAP4.error:
        typ = "NO"
    if typ != "OK":
        return 0

    uidvalidity = _response_number(M, "UIDVALIDITY")
    uidnext = _response_number(M, "UIDNEXT")
    if uidvalidity is None:
        detail = "folder did not report UIDVALIDITY; watermark left unchanged"
        print(f"  [skip] {addr} [{folder}]: {detail}")
        store.log_run(f"inbox:{addr}:{folder}", 0, "error")
        store.set_source_health(
            f"inbox:{addr}:{folder}", provider="imap", slug=folder,
            status="error", detail=detail,
        )
        raise _InboxStateError(detail)

    stored_uidvalidity = store.meta_get(validity_marker)
    epoch_changed = bool(
        stored_last_uid and str(uidvalidity) != (stored_uidvalidity or "")
    )
    scan_last_uid = 0 if (backfill or since or epoch_changed) else stored_last_uid
    recovery_days = int(cfg.get("inbox", {}).get("uid_recovery_days", 30))
    scan_lookback_days = recovery_days if epoch_changed and not (backfill or since) else lookback_days

    kept = 0
    scanned = 0
    max_uid = 0 if epoch_changed else stored_last_uid
    uids = _search_uids(M, scan_last_uid, since, scan_lookback_days,
                        backfill or epoch_changed)
    for uid in uids:
        scanned += 1
        u = int(uid)
        if u > max_uid:
            max_uid = u
        try:
            ev = _process_uid(
                M, addr, uid, store, cfg, job_index, campaign_reply_watches,
                dry_run=dry_run, rescore=backfill,
            )
        except _TransientIMAPError:
            raise
        except Exception:  # noqa: BLE001 - one bad message never sinks the run
            ev = None
        if ev is not None:
            kept += 1
    if not dry_run:
        if epoch_changed and uidnext is not None:
            max_uid = max(max_uid, uidnext - 1)
        if max_uid != stored_last_uid or epoch_changed:
            store.meta_set(marker, str(max_uid))
        store.meta_set(validity_marker, str(uidvalidity))
    status = "recovered" if epoch_changed else "ok"
    store.log_run(f"inbox:{addr}:{folder}", kept, status)
    store.set_source_health(
        f"inbox:{addr}:{folder}", provider="imap", slug=folder,
        status=status, item_count=scanned, attempts=1,
        detail=(f"UIDVALIDITY changed; replayed the last {scan_lookback_days} day(s)"
                if epoch_changed else ""),
    )
    tag = "" if folder == "INBOX" else f" [{folder}]"
    print(f"  [{addr}]{tag} {scanned} scanned / {kept} job-related"
          + (" (dry-run)" if dry_run else ""))
    return kept


def _search_uids(M, last_uid: int, since: Optional[str], lookback_days: int,
                 backfill: bool) -> list[bytes]:
    try:
        if last_uid and not backfill and not since:
            typ, data = M.uid("search", None, "UID", f"{last_uid + 1}:*")
        else:
            date = _imap_since(since, lookback_days)
            typ, data = M.uid("search", None, "SINCE", date)
    except imaplib.IMAP4.abort:
        raise
    except (imaplib.IMAP4.error, OSError) as exc:
        raise _TransientIMAPError(f"IMAP UID search failed: {exc}") from exc
    if typ != "OK":
        raise _TransientIMAPError(f"IMAP UID search failed: {typ}")
    if not data:
        raise _TransientIMAPError("IMAP UID search returned no response")
    if not data[0]:
        return []
    # "n:*" always returns at least the highest message even when none are new;
    # filter to strictly-new UIDs.
    return [u for u in data[0].split() if int(u) > last_uid]


def _process_uid(M, addr: str, uid, store, cfg: dict, job_index: dict,
                 campaign_reply_watches: list[dict],
                 *, dry_run: bool, rescore: bool = False) -> Optional[MailEvent]:
    uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)

    hdr = _fetch_headers(M, uid)
    if hdr is None:
        return None
    from_raw = _dh(hdr.get("From", ""))
    subject = _dh(hdr.get("Subject", ""))
    from_name, from_addr = _eu.parseaddr(from_raw)
    from_domain = from_addr.split("@")[-1].lower() if "@" in from_addr else ""
    message_date = _parse_date(hdr.get("Date", ""))
    campaign_reply = _is_campaign_reply_candidate(
        from_addr, message_date, campaign_reply_watches,
    )

    # Skip job-board digests / alerts / community mail (not application status),
    # and newsletter/content platforms (Substack/Medium/...) whose subjects
    # collide with lifecycle keywords (a "Coding Challenge" digest reads as an
    # assessment) -- dropped by domain even when they score a strong signal.
    if mailrules.is_noise_sender(from_name, from_addr) or mailrules.is_newsletter_domain(from_domain):
        return None
    # OTP / email-verification / password-reset mail is account plumbing, not an
    # application-status update -- drop it cheaply on the subject before any body fetch.
    if mailrules.is_transactional(subject):
        return None

    # Cheap first pass on headers only; skip clearly-irrelevant mail from
    # non-ATS domains without ever fetching a body.
    sig = mailrules.classify_signal(from_addr, subject, "")
    if (not campaign_reply and not mailrules.is_job_related(from_domain, sig)
            and not mailrules.is_ats_domain(from_domain)):
        return None

    configured_limit = int(cfg.get("inbox", {}).get("classification_chars", 6000))
    snippet = _fetch_snippet(M, uid, limit=max(1500, min(configured_limit, 20000)))
    if mailrules.is_transactional(subject, snippet):
        return None  # some OTP/verification mail carries the tell only in the body
    sig, _scores, ambiguous, tied = mailrules.classify_scored(subject, snippet)
    if not campaign_reply and not mailrules.is_job_related(from_domain, sig):
        return None

    if campaign_reply:
        from jobscope.apply.campaigns import is_optout_text
        if is_optout_text(subject, snippet):
            sig = "campaign_optout"
        elif sig == "other":
            sig = "campaign_reply"

    company, role = mailrules.parse_company_role(from_name, from_domain, subject, snippet)

    # Deterministic weights decide the vast majority; only a genuine tie (>=2
    # close verdicts) defers to the optional quorum layer (gated, None-safe).
    if ambiguous and not sig.startswith("campaign_"):
        sig = _quorum_pick(cfg, store, subject, snippet, tied) or sig

    job_id = _link_job(company, role, job_index)
    ev = MailEvent(
        account=addr, uid=uid_s, message_id=(hdr.get("Message-ID") or "").strip(),
        thread_id=_thread_key(hdr, subject),
        from_addr=from_addr, from_name=from_name, from_domain=from_domain,
        subject=subject, date=message_date,
        company=company, role=role, signal=sig, job_id=job_id,
        snippet=(snippet[:500] if cfg.get("inbox", {}).get("store_snippets", False) else ""),
        first_seen=now_iso(),
    ).ensure_id()

    if dry_run:
        print(f"    [{sig:<12}] {company or '?':<24} | {subject[:56]}")
        return ev

    is_new = store.upsert_mail_event(ev)
    if is_new:
        _apply_to_application(store, ev)
        return ev
    if rescore:
        # Re-scan mode (backfill): the message is already stored, so upsert is a
        # no-op -- but re-score its signal from the freshly-fetched body so rule
        # changes heal old events (e.g. a mis-tagged interview -> confirmation).
        # The funnel is rebuilt from these signals by the reclassify pass that
        # follows, so only the event's classification needs to be made current.
        store.update_mail_event(ev.id, signal=sig, job_id=job_id)
        return ev
    return None


def _is_campaign_reply_candidate(
    from_addr: str, message_date: str, watches: list[dict],
) -> bool:
    """Match only non-automated, post-send mail on a confirmed campaign domain."""
    if not from_addr or not message_date:
        return False
    try:
        event_at = _dt.datetime.fromisoformat(message_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    from jobscope.apply.outreach import valid_company_recipient
    for watch in watches:
        domain = str(watch.get("domain") or "")
        sent_raw = str(watch.get("sent_at") or "")
        if not valid_company_recipient(from_addr, domain):
            continue
        try:
            sent_at = _dt.datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if event_at.tzinfo is None:
            event_at = event_at.replace(tzinfo=_dt.timezone.utc)
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=_dt.timezone.utc)
        if event_at > sent_at:
            return True
    return False


def _link_job(company: str, role: str, job_index: dict) -> str:
    """Link to an existing scraped job by fuzzy company, else a stable synthetic
    key so email-only applications still dedupe across runs."""
    match = mailrules.best_company_match(company, list(job_index.keys())) if company else None
    if match:
        return job_index[match]
    basis = f"{mailrules.normalize_company(company)}|{(role or '').lower().strip()}"
    return "mail:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _apply_to_application(store, ev: MailEvent) -> None:
    status = mailrules.signal_to_status(ev.signal)
    if not status:
        return  # 'other'/'recruiter'-only noise: recorded as an event, no funnel change
    existing = store.get_application(ev.job_id) or {}
    new_status = mailrules.advance_status(existing.get("status", ""), status)
    applied_at = existing.get("applied_at", "")
    if new_status == "applied" and not applied_at:
        applied_at = ev.date or now_iso()
    store.set_application(Application(
        job_id=ev.job_id,
        status=new_status,
        package_dir=existing.get("package_dir", ""),
        resume_path=existing.get("resume_path", ""),
        cover_path=existing.get("cover_path", ""),
        applied_at=applied_at,
        notes=existing.get("notes", ""),
        company=ev.company,
        title=ev.role,
        source="inbox" if not existing else "",
    ))


def _quorum_pick(cfg: dict, store, subject: str, snippet: str,
                 candidates: list[str]) -> Optional[str]:
    """Break a keyword-scoring tie: ask the optional AI/quorum layer to choose
    among the tied candidate labels. Returns a candidate or None (AI off/unsure).
    Constrained to the tied labels so quorum only arbitrates, never invents."""
    try:
        from jobscope.core import ai
    except ImportError:
        return None
    if not ai.available(cfg) or len(candidates) < 2:
        return None
    allowed = ", ".join(candidates)
    system = ("You label job-application emails. The keyword classifier is torn "
              f"between exactly these labels: {allowed}. Reply with one of them, "
              "lowercase, no punctuation.")
    user = f"Subject: {subject}\n\n{snippet[:1200]}"
    out = ai.chat(cfg, store, system, user, cache=True,
                  strategy=ai.strategy_for(cfg, "classify"))
    if not out:
        return None
    word = out.strip().split()[0].lower().strip(".,!") if out.strip() else ""
    return word if word in candidates else None


# --- IMAP fetch + MIME helpers ---------------------------------------------
def _fetch_headers(M, uid):
    try:
        typ, data = M.uid("fetch", uid, _HEADER_FIELDS)
    except imaplib.IMAP4.abort:
        raise
    except (imaplib.IMAP4.error, OSError) as exc:
        raise _TransientIMAPError(
            f"IMAP header fetch failed for UID {uid!r}: {exc}") from exc
    if typ != "OK" or not data or not data[0] or not isinstance(data[0], tuple):
        raise _TransientIMAPError(f"IMAP header fetch failed for UID {uid!r}: {typ}")
    return _email.message_from_bytes(data[0][1])


def _fetch_snippet(M, uid, limit: int = 1500) -> str:
    try:
        typ, data = M.uid("fetch", uid, "(BODY.PEEK[])")
    except imaplib.IMAP4.abort:
        raise
    except (imaplib.IMAP4.error, OSError) as exc:
        raise _TransientIMAPError(
            f"IMAP body fetch failed for UID {uid!r}: {exc}") from exc
    if typ != "OK" or not data or not data[0] or not isinstance(data[0], tuple):
        raise _TransientIMAPError(f"IMAP body fetch failed for UID {uid!r}: {typ}")
    msg = _email.message_from_bytes(data[0][1])
    return _strip_html(_extract_text(msg))[:limit]


def _extract_text(msg) -> str:
    if msg.is_multipart():
        plain, html = "", ""
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and not plain:
                plain = _decode_part(part)
            elif ctype == "text/html" and not html:
                html = _decode_part(part)
        return plain or html
    return _decode_part(msg)


def _decode_part(part) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return ""


def _dh(raw: str) -> str:
    """Decode an RFC 2047 encoded-word header to a plain string."""
    try:
        return str(make_header(decode_header(raw or "")))
    except (ValueError, TypeError):
        return raw or ""


def _thread_key(hdr, subject: str) -> str:
    refs = (hdr.get("References") or "").split()
    if refs:
        return refs[0].strip("<>")
    irt = (hdr.get("In-Reply-To") or "").strip().strip("<>")
    if irt:
        return irt
    return "subj:" + mailrules.normalize_subject(subject)


def _parse_date(raw: str) -> str:
    try:
        d = _eu.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if d is None:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _imap_since(since: Optional[str], lookback_days: int) -> str:
    if since:
        try:
            d = _dt.datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            d = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    else:
        d = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    return d.strftime("%d-%b-%Y")
