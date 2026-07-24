import json
import threading
import urllib.error
import urllib.request

from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, MailEvent, Resume
from jobscope.core.store import Store
from jobscope.deliver import serve


def _cfg(tmp_path):
    cfg = load_config(None)
    cfg["output"]["db_path"] = str(tmp_path / "campaign-api.db")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    cfg["serve"]["web_dist"] = str(dist)
    return cfg


def _request(method, url, *, token="", body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Refresh-Token"] = token
        headers["Origin"] = url.split("/api/", 1)[0]
    request = urllib.request.Request(
        url, method=method, headers=headers,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))
    return response.status, json.loads(response.read().decode("utf-8"))


def test_campaign_api_is_local_token_guarded_and_rejects_unknown_fields(tmp_path):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()
    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, denied = _request("GET", base + "/api/campaigns")
        assert code == 403 and denied["error"] == "forbidden"
        code, denied = _request("GET", base + "/api/engagements")
        assert code == 403 and denied["error"] == "forbidden"

        code, activity = _request("GET", base + "/api/engagements", token=token)
        assert code == 200 and activity == {"ok": True, "engagements": []}

        code, created = _request(
            "POST", base + "/api/campaigns", token=token,
            body={"name": "India security", "requested_count": 2},
        )
        assert code == 200 and created["ok"] is True
        assert len(created["targets"]) == 2
        campaign_id = created["campaign"]["id"]

        code, listing = _request("GET", base + "/api/campaigns", token=token)
        assert code == 200 and listing["campaigns"][0]["id"] == campaign_id

        code, detail = _request(
            "GET", base + f"/api/campaigns/detail?id={campaign_id}", token=token,
        )
        assert code == 200 and detail["campaign"]["id"] == campaign_id

        code, tracking = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "check_replies", "fetch": True},
        )
        assert code == 200 and tracking["ok"] is True
        assert tracking["inbox_status"] == "not_needed"

        code, rejected = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "approve", "target_id": "missing", "force": True},
        )
        assert code == 400 and "unknown action field" in rejected["error"]

        code, deleted = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "delete", "campaign_id": campaign_id},
        )
        assert code == 200 and deleted["deleted_campaign_id"] == campaign_id
        code, listing = _request("GET", base + "/api/campaigns", token=token)
        assert code == 200 and listing["campaigns"] == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_campaign_api_builds_followup_queue_without_sending(tmp_path):
    cfg = _cfg(tmp_path)
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Jane\n", encoding="utf-8")
    with Store(cfg["output"]["db_path"]) as store:
        store.save_resume(Resume(
            full_name="Jane", skills=["security"], source_path=str(resume_path),
        ))
        job = Job(
            source="test", title="Security Engineer", company="Acme",
            company_url="https://acme.example", url="https://acme.example/job",
        ).ensure_id()
        store.upsert_job(job)
        store.set_application(Application(
            job_id=job.id, status="applied", company=job.company,
            applied_at="2020-01-01T00:00:00Z",
        ))
        store.set_company_contacts(job.company, "acme.example", [{
            "email": "recruiter@acme.example", "source": "hunter",
            "confidence": "medium", "note": "recruiter",
        }])
    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, result = _request(
            "POST", base + "/api/campaigns", token=token,
            body={
                "name": "Application follow-ups", "requested_count": 10,
                "purpose": "followup", "include_cold": False,
                "include_applications": True,
            },
        )
        assert code == 200 and result["campaign"]["purpose"] == "followup"
        assert result["counts"] == {"draft": 1}
        assert result["targets"][0]["state"] == "draft"
        assert not result["targets"][0]["approved_at"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_campaign_send_now_routes_to_isolated_manual_send(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()
    captured = {}

    def manual_send(_cfg, _store, target_id, **kwargs):
        captured.update({"target_id": target_id, **kwargs})
        return {"ok": True, "sent": True}

    monkeypatch.setattr("jobscope.apply.campaigns.send_target", manual_send)
    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, result = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "send_now", "target_id": "target:one"},
        )
        assert code == 200 and result == {"ok": True, "sent": True}
        assert captured == {
            "target_id": "target:one", "ignore_schedule": True,
            "allow_inactive": True,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_engagement_api_omits_outbound_secrets_and_summarizes_reply(tmp_path):
    cfg = _cfg(tmp_path)
    resume_path = tmp_path / "PRIVATE-RESUME-CANARY.md"
    resume_path.write_text("# Private", encoding="utf-8")
    with Store(cfg["output"]["db_path"]) as store:
        campaign = store.create_outreach_campaign("Cold", 1, purpose="cold")
        target = store.upsert_outreach_campaign_target(
            campaign["id"], "Acme", "acme",
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email="recruiter@acme.example",
            subject="Security introduction", body="PRIVATE-BODY-CANARY",
            resume_path=str(resume_path),
        )
        store.approve_outreach_campaign_target(target["id"])
        assert store.claim_outreach_campaign_target_send(
            target["id"], "PRIVATE-MESSAGE-ID@example.test",
        )
        store.mark_outreach_campaign_target_sent(target["id"], "2026-07-17T05:30:00Z")
        reply = MailEvent(
            account="me@example.com", message_id="<PRIVATE-REPLY-ID@example.test>",
            from_addr="recruiter@acme.example", from_domain="acme.example",
            subject="Re: Security introduction", date="2026-07-17T06:00:00Z",
            signal="campaign_reply", snippet="Thanks, let us schedule a call.",
        ).ensure_id()
        store.upsert_mail_event(reply)
        store.mark_outreach_campaign_target_reply(
            target["id"], reply.date, event_id=reply.id,
        )

    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, result = _request("GET", base + "/api/engagements", token=token)
        assert code == 200
        assert result["engagements"][0]["events"][-1]["summary"] == (
            "Thanks, let us schedule a call."
        )
        serialized = json.dumps(result)
        for canary in (
            "PRIVATE-BODY-CANARY", "PRIVATE-RESUME-CANARY",
            "PRIVATE-MESSAGE-ID", "PRIVATE-REPLY-ID",
        ):
            assert canary not in serialized
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_engagement_api_does_not_echo_private_exception_text(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()
    monkeypatch.setattr(
        "jobscope.apply.campaigns.engagement_activity",
        lambda _store: (_ for _ in ()).throw(RuntimeError("PRIVATE-DB-PATH-CANARY")),
    )
    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, result = _request("GET", base + "/api/engagements", token=token)
        assert code == 500
        assert result == {"ok": False, "error": "could not load engagement activity"}
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)