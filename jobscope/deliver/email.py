"""Email summaries via SMTP (optional).

Off unless `email.enabled` is true and from/to/password are set. The password is
read from the environment (see `email.password_env`), never the config file.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jobscope.core.config import smtp_password


def send(cfg: dict, subject: str, text: str, html: Optional[str] = None, *,
         to: Optional[str] = None, attachments: Optional[list[str]] = None) -> bool:
    ec = cfg.get("email", {})
    if not ec.get("enabled"):
        return False
    pw = smtp_password(cfg)
    recipient = to or ec.get("to_addr")
    if not (ec.get("from_addr") and recipient and pw):
        print("  [email] enabled but from/to/password missing; skipping")
        return False

    if attachments:
        msg = MIMEMultipart("mixed")
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(text, "plain", "utf-8"))
        if html:
            body.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(body)
        for path in attachments:
            _attach(msg, path)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))
    msg["Subject"] = subject
    msg["From"] = ec["from_addr"]
    msg["To"] = recipient

    try:
        with smtplib.SMTP(ec["smtp_host"], int(ec["smtp_port"]), timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(ec["from_addr"], pw)
            s.sendmail(ec["from_addr"], [recipient], msg.as_string())
        print(f"  [email] sent to {recipient}")
        return True
    except Exception as e:  # noqa: BLE001 - email is optional
        print(f"  [email] error: {e}")
        return False


def _attach(msg: MIMEMultipart, path: str) -> None:
    """Attach a file to a multipart/mixed message (best-effort; skips if missing)."""
    if not path or not os.path.exists(path):
        return
    with open(path, "rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
    msg.attach(part)
