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
* **AI optional.** An ambiguous ``other`` classification may be refined by the
  gated AI layer, but classification never requires it.
"""
from __future__ import annotations

import datetime as _dt
import email as _email
import email.utils as _eu
import hashlib
import imaplib
from email.header import decode_header, make_header
from typing import Optional

from .ats import _strip_html
from jobscope.core.config import inbox_password
from jobscope.core.model import Application, MailEvent
from jobscope.core.store import now_iso
from . import mailrules

_HEADER_FIELDS = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO)])"


def run(cfg: dict, store, *, dry_run: bool = False, account: Optional[str] = None,
        since: Optional[str] = None, backfill: bool = False) -> int:
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
    for acct in accounts:
        total_new += _sync_account(cfg, store, acct, dry_run=dry_run, since=since,
                                   backfill=backfill)

    verb = "would ingest" if dry_run else "ingested"
    print(f"\n  inbox: {verb} {total_new} job-related email(s) across "
          f"{len(accounts)} account(s).")
    if total_new and not dry_run:
        print("  next: python -m jobscope track   |   python -m jobscope dashboard --open")
    return 0


def _sync_account(cfg: dict, store, acct: dict, *, dry_run: bool, since: Optional[str],
                  backfill: bool) -> int:
    icfg = cfg["inbox"]
    addr = (acct.get("email") or "").strip()
    pw = inbox_password(cfg, acct)
    if not addr or not pw:
        env = acct.get("password_env", "?")
        print(f"  [skip] {addr or '(no email)'}: missing app password "
              f"(set env {env} in .env)")
        return 0

    host = icfg.get("imap_host", "imap.gmail.com")
    port = int(icfg.get("imap_port", 993))
    folder = icfg.get("folder", "INBOX")
    lookback_days = int(acct.get("lookback_days", icfg.get("lookback_days", 90)))
    marker = f"inbox:{addr}:last_uid"
    last_uid = 0 if (backfill or since) else int(store.meta_get(marker, "0") or 0)

    try:
        M = imaplib.IMAP4_SSL(host, port)
    except OSError as exc:  # noqa: BLE001 - network setup is best-effort
        print(f"  [skip] {addr}: cannot reach {host}:{port} ({exc})")
        store.log_run(f"inbox:{addr}", 0, "error")
        return 0

    # Prebuild a company -> job-id index once so email->job linking is O(1)/email.
    job_index: dict[str, str] = {}
    for j in store.jobs(order_by_score=False):
        if j.company:
            job_index.setdefault(mailrules.normalize_company(j.company), j.id)

    kept = 0
    scanned = 0
    max_uid = last_uid
    try:
        M.login(addr, pw)
        M.select(folder, readonly=True)
        uids = _search_uids(M, last_uid, since, lookback_days, backfill)
        for uid in uids:
            scanned += 1
            u = int(uid)
            if u > max_uid:
                max_uid = u
            try:
                ev = _process_uid(M, addr, uid, store, cfg, job_index, dry_run=dry_run)
            except Exception:  # noqa: BLE001 - one bad message never sinks the run
                ev = None
            if ev is not None:
                kept += 1
        if not dry_run and max_uid > last_uid:
            store.meta_set(marker, str(max_uid))
        store.log_run(f"inbox:{addr}", kept, "ok")
        print(f"  [{addr}] {scanned} scanned / {kept} job-related"
              + (" (dry-run)" if dry_run else ""))
    except imaplib.IMAP4.error as exc:
        print(f"  [skip] {addr}: IMAP login/select failed ({exc}). "
              f"Check the app password and that IMAP is enabled.")
        store.log_run(f"inbox:{addr}", 0, "error")
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
    return kept


def _search_uids(M, last_uid: int, since: Optional[str], lookback_days: int,
                 backfill: bool) -> list[bytes]:
    if last_uid and not backfill and not since:
        typ, data = M.uid("search", None, "UID", f"{last_uid + 1}:*")
    else:
        date = _imap_since(since, lookback_days)
        typ, data = M.uid("search", None, "SINCE", date)
    if typ != "OK" or not data or not data[0]:
        return []
    # "n:*" always returns at least the highest message even when none are new;
    # filter to strictly-new UIDs.
    return [u for u in data[0].split() if int(u) > last_uid]


def _process_uid(M, addr: str, uid, store, cfg: dict, job_index: dict,
                 *, dry_run: bool) -> Optional[MailEvent]:
    uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)

    hdr = _fetch_headers(M, uid)
    if hdr is None:
        return None
    from_raw = _dh(hdr.get("From", ""))
    subject = _dh(hdr.get("Subject", ""))
    from_name, from_addr = _eu.parseaddr(from_raw)
    from_domain = from_addr.split("@")[-1].lower() if "@" in from_addr else ""

    # Skip job-board digests / alerts / community mail (not application status).
    if mailrules.is_noise_sender(from_name, from_addr):
        return None

    # Cheap first pass on headers only; skip clearly-irrelevant mail from
    # non-ATS domains without ever fetching a body.
    sig = mailrules.classify_signal(from_addr, subject, "")
    if not mailrules.is_job_related(from_domain, sig) and not mailrules.is_ats_domain(from_domain):
        return None

    snippet = _fetch_snippet(M, uid)
    sig = mailrules.classify_signal(from_addr, subject, snippet)
    if not mailrules.is_job_related(from_domain, sig):
        return None

    company, role = mailrules.parse_company_role(from_name, from_domain, subject, snippet)

    # Optional AI refinement for the residual "other" bucket (gated, None-safe).
    if sig == "other":
        sig = _ai_refine(cfg, store, subject, snippet) or "other"

    job_id = _link_job(company, role, job_index)
    ev = MailEvent(
        account=addr, uid=uid_s, message_id=(hdr.get("Message-ID") or "").strip(),
        thread_id=_thread_key(hdr, subject),
        from_addr=from_addr, from_name=from_name, from_domain=from_domain,
        subject=subject, date=_parse_date(hdr.get("Date", "")),
        company=company, role=role, signal=sig, job_id=job_id,
        snippet=snippet[:500], first_seen=now_iso(),
    ).ensure_id()

    if dry_run:
        print(f"    [{sig:<12}] {company or '?':<24} | {subject[:56]}")
        return ev

    is_new = store.upsert_mail_event(ev)
    if is_new:
        _apply_to_application(store, ev)
    return ev if is_new else None


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


def _ai_refine(cfg: dict, store, subject: str, snippet: str) -> Optional[str]:
    """Ask the optional AI layer to bucket an ambiguous email. Returns a valid
    signal or None (when AI is disabled, unreachable, or unsure)."""
    try:
        from jobscope.core import ai
    except ImportError:
        return None
    if not ai.available(cfg):
        return None
    allowed = "confirmation, recruiter, assessment, interview, offer, rejection, other"
    system = ("You label job-application emails. Reply with exactly one word from: "
              f"{allowed}. No punctuation.")
    user = f"Subject: {subject}\n\n{snippet[:1200]}"
    out = ai.chat(cfg, store, system, user, cache=True)
    if not out:
        return None
    word = out.strip().split()[0].lower().strip(".,!") if out.strip() else ""
    return word if word in mailrules.SIGNALS else None


# --- IMAP fetch + MIME helpers ---------------------------------------------
def _fetch_headers(M, uid):
    typ, data = M.uid("fetch", uid, _HEADER_FIELDS)
    if typ != "OK" or not data or not data[0] or not isinstance(data[0], tuple):
        return None
    return _email.message_from_bytes(data[0][1])


def _fetch_snippet(M, uid, limit: int = 1500) -> str:
    typ, data = M.uid("fetch", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data or not data[0] or not isinstance(data[0], tuple):
        return ""
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
