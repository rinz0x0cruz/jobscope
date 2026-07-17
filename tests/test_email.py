from jobscope.deliver import email


def test_email_send_includes_campaign_message_id(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self, **_kwargs):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, sender, recipients, message):
            sent.update(sender=sender, recipients=recipients, message=message)

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    cfg = {
        "email": {
            "enabled": True, "from_addr": "me@example.com",
            "smtp_host": "smtp.example.com", "smtp_port": 587,
        },
    }

    assert email.send(
        cfg, "Subject", "Body", to="recruiter@acme.example",
        message_id="jobscope-campaign-123@example.com",
    ) is True
    assert "Message-ID: <jobscope-campaign-123@example.com>" in sent["message"]
    assert sent["recipients"] == ["recruiter@acme.example"]


def test_email_classifies_sendmail_exception_as_unknown_without_leaking_detail(monkeypatch):
    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self, **_kwargs):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, *_args):
            raise RuntimeError("contains-sensitive-provider-detail")

    monkeypatch.setattr(email, "smtp_password", lambda _cfg: "resolved")
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    cfg = {"email": {"enabled": True, "from_addr": "me@example.com",
                     "smtp_host": "smtp.example.com", "smtp_port": 587}}

    try:
        email.send(cfg, "Subject", "Body", to="recruiter@acme.example", raise_errors=True)
    except email.EmailDeliveryError as error:
        assert error.outcome_unknown is True
        assert str(error) == "RuntimeError"
    else:
        raise AssertionError("delivery error was not raised")