"""Email summaries via SMTP (optional).

Off unless `email.enabled` is true and from/to/password are set. The password is
read from the environment (see `email.password_env`), never the config file.
"""
from __future__ import annotations

import os
import mimetypes
import smtplib
import socket
import ssl
from datetime import datetime, timezone
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, getaddresses, make_msgid
from typing import Optional

from jobscope.core.config import smtp_password


class EmailDeliveryError(RuntimeError):
    """SMTP failure with an explicit external-effect outcome classification."""

    def __init__(
        self, detail: str, *, outcome: str = "",
        outcome_unknown: Optional[bool] = None, accepted: bool = False,
    ):
        super().__init__(detail)
        if not outcome:
            outcome = "delivery_unknown" if outcome_unknown else "pre_send_failure"
        self.outcome = outcome
        self.outcome_unknown = outcome in {"delivery_unknown", "partial_recipient"}
        self.accepted = accepted


def _safe_smtp_error(exc: Exception) -> str:
    code = getattr(exc, "smtp_code", None)
    return f"{type(exc).__name__}{f' ({code})' if code else ''}"


def build_message(
    cfg: dict, subject: str, text: str, html: Optional[str] = None, *,
    to: Optional[str] = None, from_addr: str = "",
    attachments: Optional[list[str]] = None,
    message_id: str = "", in_reply_to: str = "", references: str = "",
) -> EmailMessage:
    """Build the exact MIME message used by SMTP and offline EML export."""
    ec = cfg.get("email", {}) or {}
    sender = (from_addr or ec.get("from_addr") or "").strip()
    recipient = (to or ec.get("to_addr") or "").strip()
    if not sender or not recipient:
        raise ValueError("sender and recipient addresses are required")
    msg = EmailMessage(policy=SMTP)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    sender_domain = sender.rsplit("@", 1)[-1] if "@" in sender else None
    msg["Message-ID"] = (
        f"<{message_id.strip().strip('<>')}>"
        if message_id else make_msgid(domain=sender_domain)
    )
    if in_reply_to:
        msg["In-Reply-To"] = f"<{in_reply_to.strip().strip('<>')}>"
    if references:
        msg["References"] = " ".join(
            f"<{value.strip().strip('<>')}>"
            for value in references.split()
            if value.strip().strip("<>")
        )
    for name in ("From", "To", "Message-ID"):
        if getattr(msg[name], "defects", ()):
            raise ValueError(f"invalid {name} header")
    msg.set_content(text or "")
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        _attach(msg, path)
    return msg


def write_eml(
    cfg: dict, path: str, subject: str, text: str, html: Optional[str] = None, **kwargs,
) -> str:
    """Write one MIME message for explicit offline review without SMTP."""
    msg = build_message(cfg, subject, text, html, **kwargs)
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "xb") as handle:
        handle.write(msg.as_bytes())
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def send(cfg: dict, subject: str, text: str, html: Optional[str] = None, *,
         to: Optional[str] = None, attachments: Optional[list[str]] = None,
         message_id: str = "", in_reply_to: str = "", references: str = "",
         raise_errors: bool = False) -> bool:
    ec = cfg.get("email", {})
    if not ec.get("enabled"):
        return False
    pw = smtp_password(cfg)
    recipient = to or ec.get("to_addr")
    if not (ec.get("from_addr") and recipient and pw):
        print("  [email] enabled but from/to/password missing; skipping")
        return False
    server = None
    phase = "connect"
    accepted = False
    try:
        msg = build_message(
            cfg, subject, text, html, to=recipient, attachments=attachments,
            message_id=message_id, in_reply_to=in_reply_to, references=references,
        )
        recipients = _recipient_addresses(recipient)
        server = smtplib.SMTP(ec["smtp_host"], int(ec["smtp_port"]), timeout=20)
        phase = "tls"
        server.ehlo()
        if not server.has_extn("starttls"):
            raise smtplib.SMTPNotSupportedError("STARTTLS is required")
        server.starttls(context=ssl.create_default_context())
        phase = "auth"
        server.ehlo()
        if not server.has_extn("auth"):
            raise smtplib.SMTPNotSupportedError("AUTH is required")
        server.login(ec["from_addr"], pw)
        phase = "submit"
        refused = server.send_message(
            msg, from_addr=ec["from_addr"], to_addrs=recipients,
        )
        accepted = True
        if refused:
            raise EmailDeliveryError(
                "partial recipient acceptance", outcome="partial_recipient",
                accepted=True,
            )
        print("  [email] accepted by submission MTA")
        return True
    except EmailDeliveryError as exc:
        print(f"  [email] error: {exc.outcome}")
        if raise_errors:
            raise
        return False
    except Exception as e:  # noqa: BLE001 - email is optional
        detail = _safe_smtp_error(e)
        print(f"  [email] error: {detail}")
        if raise_errors:
            raise EmailDeliveryError(
                detail, outcome=_failure_outcome(e, phase), accepted=False,
            ) from e
        return False
    finally:
        if server is not None:
            if accepted:
                try:
                    server.quit()
                except Exception:  # acceptance already established
                    pass
            else:
                try:
                    server.close()
                except Exception:
                    pass


def preflight(cfg: dict, *, message_size: int = 0) -> dict:
    """Verify SMTP submission capabilities without issuing MAIL/RCPT/DATA."""
    ec = cfg.get("email", {}) or {}
    sender = str(ec.get("from_addr") or "").strip()
    password = smtp_password(cfg)
    if not (ec.get("smtp_host") and ec.get("smtp_port") and sender and password):
        return {"ok": False, "code": "unconfigured"}
    try:
        Address(addr_spec=sender)
    except (TypeError, ValueError):
        return {"ok": False, "code": "invalid_sender"}
    server = None
    phase = "connect"
    try:
        server = smtplib.SMTP(ec["smtp_host"], int(ec["smtp_port"]), timeout=20)
        phase = "tls"
        server.ehlo()
        if not server.has_extn("starttls"):
            return {"ok": False, "code": "starttls_required"}
        server.starttls(context=ssl.create_default_context())
        phase = "auth"
        server.ehlo()
        if not server.has_extn("auth"):
            return {"ok": False, "code": "auth_required"}
        size_limit = _size_limit(server)
        server.login(sender, password)
        phase = "noop"
        code, _response = server.noop()
        if not 200 <= int(code) < 300:
            return {"ok": False, "code": "noop_failed", "smtp_code": int(code)}
        if message_size > 0 and not size_limit:
            return {"ok": False, "code": "size_unavailable"}
        if message_size > 0 and size_limit and message_size > size_limit:
            return {
                "ok": False, "code": "message_too_large",
                "size_limit": size_limit,
            }
        return {
            "ok": True, "code": "ready", "starttls": True,
            "auth": True, "size_limit": size_limit,
        }
    except Exception as exc:  # noqa: BLE001 - return bounded capability evidence
        return {
            "ok": False, "code": _failure_outcome(exc, phase),
            **({"smtp_code": int(exc.smtp_code)} if getattr(exc, "smtp_code", None) else {}),
        }
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


def _recipient_addresses(value: str) -> list[str]:
    addresses = [address for _name, address in getaddresses([value]) if address]
    if not addresses:
        raise ValueError("at least one recipient address is required")
    return addresses


def _failure_outcome(exc: Exception, phase: str) -> str:
    if phase != "submit":
        return "pre_send_failure"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [int(value[0]) for value in exc.recipients.values()]
        return "permanent_rejection" if codes and all(code >= 500 for code in codes) else "transient_rejection"
    if isinstance(exc, smtplib.SMTPResponseException):
        code = int(exc.smtp_code)
        if 400 <= code < 500:
            return "transient_rejection"
        if 500 <= code < 600:
            return "permanent_rejection"
        return "delivery_unknown"
    if isinstance(exc, (TimeoutError, socket.timeout, smtplib.SMTPServerDisconnected, OSError)):
        return "delivery_unknown"
    return "delivery_unknown"


def _size_limit(server) -> int:
    raw = str((getattr(server, "esmtp_features", {}) or {}).get("size") or "").strip()
    try:
        return max(0, int(raw.split()[0])) if raw else 0
    except (TypeError, ValueError):
        return 0


def _attach(msg: EmailMessage, path: str) -> None:
    """Attach one explicit file with a truthful MIME type and filename."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path or "attachment path is empty")
    with open(path, "rb") as fh:
        payload = fh.read()
    content_type, encoding = mimetypes.guess_type(path)
    if not content_type or encoding:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)
    msg.add_attachment(
        payload, maintype=maintype, subtype=subtype,
        filename=os.path.basename(path),
    )
