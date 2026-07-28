import hashlib
import smtplib

import pytest

from jobscope.deliver import email


def _cfg():
    return {
        "email": {
            "enabled": True,
            "from_addr": "me@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
        },
    }


class _ReadySMTP:
    instances = []

    def __init__(self, *_args, **_kwargs):
        self.calls = []
        self.esmtp_features = {
            "starttls": "",
            "auth": "PLAIN LOGIN",
            "size": "4096",
        }
        type(self).instances.append(self)

    def ehlo(self):
        self.calls.append("ehlo")
        return 250, b"ok"

    def has_extn(self, name):
        return name in self.esmtp_features

    def starttls(self, **_kwargs):
        self.calls.append("starttls")
        return 220, b"ready"

    def login(self, *_args):
        self.calls.append("login")
        return 235, b"ok"

    def send_message(self, *_args, **_kwargs):
        self.calls.append("send_message")
        return {}

    def noop(self):
        self.calls.append("noop")
        return 250, b"ok"

    def quit(self):
        self.calls.append("quit")
        return 221, b"bye"

    def close(self):
        self.calls.append("close")


def test_email_send_includes_campaign_message_id(monkeypatch):
    sent = {}

    class FakeSMTP(_ReadySMTP):
        def send_message(self, message, *, from_addr, to_addrs):
            self.calls.append("send_message")
            sent.update(sender=from_addr, recipients=to_addrs, message=message)
            return {}

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    assert email.send(
        _cfg(), "Subject", "Body", to="recruiter@acme.example",
        message_id="jobscope-campaign-123@example.com",
        in_reply_to="parent@example.com",
        references="root@example.com parent@example.com",
    ) is True
    assert sent["message"]["Message-ID"] == "<jobscope-campaign-123@example.com>"
    assert sent["message"]["In-Reply-To"] == "<parent@example.com>"
    assert sent["message"]["References"] == "<root@example.com> <parent@example.com>"
    assert sent["message"]["Date"]
    assert sent["recipients"] == ["recruiter@acme.example"]


def test_email_classifies_sendmail_exception_as_unknown_without_leaking_detail(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        def send_message(self, *_args, **_kwargs):
            raise RuntimeError("contains-sensitive-provider-detail")

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(
            _cfg(), "Subject", "Body", to="recruiter@acme.example",
            raise_errors=True,
        )

    assert raised.value.outcome == "delivery_unknown"
    assert raised.value.outcome_unknown is True
    assert str(raised.value) == "RuntimeError"


def test_build_message_adds_structural_headers_and_exact_attachment(tmp_path):
    content = b"resume-content\x00\xff"
    attachment = tmp_path / "resume.pdf"
    attachment.write_bytes(content)

    message = email.build_message(
        _cfg(), "Subject", "Plain", "<p>HTML</p>",
        to="recruiter@acme.example", attachments=[str(attachment)],
    )

    assert message["Date"]
    assert str(message["Message-ID"]).startswith("<")
    assert str(message["Message-ID"]).endswith("@example.com>")
    assert b"\r\n" in message.as_bytes()
    parts = list(message.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "resume.pdf"
    decoded = parts[0].get_payload(decode=True)
    assert decoded == content
    assert hashlib.sha256(decoded).digest() == hashlib.sha256(content).digest()


def test_build_message_generates_unique_ids_and_rejects_invalid_supplied_id():
    first = email.build_message(
        _cfg(), "Subject", "Body", to="recruiter@acme.example",
    )
    second = email.build_message(
        _cfg(), "Subject", "Body", to="recruiter@acme.example",
    )

    assert first["Message-ID"] != second["Message-ID"]
    with pytest.raises(ValueError, match="invalid Message-ID header"):
        email.build_message(
            _cfg(), "Subject", "Body", to="recruiter@acme.example",
            message_id="not a valid id",
        )


@pytest.mark.parametrize(
    ("smtp_error", "outcome"),
    [
        (smtplib.SMTPDataError(451, b"try later"), "transient_rejection"),
        (smtplib.SMTPDataError(550, b"rejected"), "permanent_rejection"),
        (smtplib.SMTPServerDisconnected("closed"), "delivery_unknown"),
    ],
)
def test_email_classifies_submission_failures(monkeypatch, smtp_error, outcome):
    class FakeSMTP(_ReadySMTP):
        def send_message(self, *_args, **_kwargs):
            raise smtp_error

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(
            _cfg(), "Subject", "Body", to="recruiter@acme.example",
            raise_errors=True,
        )

    assert raised.value.outcome == outcome
    assert raised.value.outcome_unknown is (outcome == "delivery_unknown")


def test_email_classifies_tls_failure_as_pre_send(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        def starttls(self, **_kwargs):
            raise OSError("private transport detail")

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(
            _cfg(), "Subject", "Body", to="recruiter@acme.example",
            raise_errors=True,
        )

    assert raised.value.outcome == "pre_send_failure"
    assert str(raised.value) == "OSError"


def test_email_treats_quit_failure_after_acceptance_as_success(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        def quit(self):
            raise smtplib.SMTPServerDisconnected("after acceptance")

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    assert email.send(
        _cfg(), "Subject", "Body", to="recruiter@acme.example",
        raise_errors=True,
    ) is True


def test_email_classifies_message_build_failure_as_pre_send(monkeypatch, tmp_path):
    smtp_calls = []
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(
        email.smtplib, "SMTP",
        lambda *_args, **_kwargs: smtp_calls.append(True),
    )

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(
            _cfg(), "Subject", "Body", to="recruiter@acme.example",
            attachments=[str(tmp_path / "missing.pdf")], raise_errors=True,
        )

    assert raised.value.outcome == "pre_send_failure"
    assert raised.value.outcome_unknown is False
    assert str(raised.value) == "FileNotFoundError"
    assert smtp_calls == []


def test_email_reports_partial_recipient_acceptance_without_retrying(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        def send_message(self, *_args, **_kwargs):
            return {"bad@example.com": (550, b"rejected")}

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(
            _cfg(), "Subject", "Body",
            to="ok@example.com, bad@example.com", raise_errors=True,
        )

    assert raised.value.outcome == "partial_recipient"
    assert raised.value.outcome_unknown is True
    assert raised.value.accepted is True


def test_preflight_authenticates_without_starting_delivery(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        pass

    FakeSMTP.instances = []
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    result = email.preflight(_cfg(), message_size=4097)

    assert result == {
        "ok": False,
        "code": "message_too_large",
        "size_limit": 4096,
    }
    assert FakeSMTP.instances[0].calls == [
        "ehlo", "starttls", "ehlo", "login", "noop", "quit",
    ]


def test_preflight_fails_closed_when_size_capacity_is_not_advertised(monkeypatch):
    class FakeSMTP(_ReadySMTP):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.esmtp_features.pop("size")

    FakeSMTP.instances = []
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    assert email.preflight(_cfg(), message_size=100) == {
        "ok": False,
        "code": "size_unavailable",
    }
    assert "send_message" not in FakeSMTP.instances[0].calls


def test_preflight_reports_bounded_code_when_connect_fails(monkeypatch):
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(
        email.smtplib, "SMTP",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("private host detail")),
    )

    result = email.preflight(_cfg())

    assert result == {"ok": False, "code": "pre_send_failure"}
    assert "private host detail" not in repr(result)


def test_send_expands_every_envelope_recipient_from_the_to_header(monkeypatch):
    sent = {}

    class FakeSMTP(_ReadySMTP):
        def send_message(self, message, *, from_addr, to_addrs):
            self.calls.append("send_message")
            sent.update(message=message, to_addrs=to_addrs)
            return {}

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)

    assert email.send(
        _cfg(), "Subject", "Body",
        to='"Acme HR" <hr@acme.example>, second@acme.example',
    ) is True
    assert sent["to_addrs"] == ["hr@acme.example", "second@acme.example"]
    assert "Acme HR" in str(sent["message"]["To"])


def test_malformed_recipient_fails_before_any_connection(monkeypatch):
    connections = []
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(
        email.smtplib, "SMTP",
        lambda *_args, **_kwargs: connections.append(True) or _ReadySMTP(),
    )

    with pytest.raises(email.EmailDeliveryError) as raised:
        email.send(_cfg(), "Subject", "Body", to="not-an-address", raise_errors=True)

    assert raised.value.outcome == "pre_send_failure"
    assert raised.value.outcome_unknown is False
    assert connections == []


def test_preflight_rejects_an_invalid_sender_before_connecting(monkeypatch):
    connections = []
    cfg = _cfg()
    cfg["email"]["from_addr"] = "jane doe@example.com"
    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(
        email.smtplib, "SMTP",
        lambda *_args, **_kwargs: connections.append(True) or _ReadySMTP(),
    )

    assert email.preflight(cfg) == {"ok": False, "code": "invalid_sender"}
    assert connections == []