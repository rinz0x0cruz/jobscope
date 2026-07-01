"""Email summaries via SMTP (optional).

Off unless `email.enabled` is true and from/to/password are set. The password is
read from the environment (see `email.password_env`), never the config file.
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .config import smtp_password


def send(cfg: dict, subject: str, text: str, html: Optional[str] = None) -> bool:
    ec = cfg.get("email", {})
    if not ec.get("enabled"):
        return False
    pw = smtp_password(cfg)
    if not (ec.get("from_addr") and ec.get("to_addr") and pw):
        print("  [email] enabled but from/to/password missing; skipping")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = ec["from_addr"]
    msg["To"] = ec["to_addr"]
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(ec["smtp_host"], int(ec["smtp_port"]), timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(ec["from_addr"], pw)
            s.sendmail(ec["from_addr"], [ec["to_addr"]], msg.as_string())
        print(f"  [email] sent to {ec['to_addr']}")
        return True
    except Exception as e:  # noqa: BLE001 - email is optional
        print(f"  [email] error: {e}")
        return False
