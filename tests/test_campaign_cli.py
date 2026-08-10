import pytest

from jobscope.apply import campaigns
from jobscope.cli import main
from jobscope.core.model import Application, Job, Resume
from jobscope.core.store import Store


@pytest.mark.parametrize("code, expected_exit", [
    ("nothing_due", 0),
    ("outside_send_window", 0),
    ("minimum_spacing", 0),
    ("daily_limit", 0),
    ("followup_not_due", 0),
    ("send_in_progress", 0),
    ("delivery_unknown", 1),
    ("smtp_failed", 1),
    ("invalid_recipient", 1),
])
def test_campaign_cli_send_approved_defers_without_reporting_failure(
    tmp_path, capsys, monkeypatch, code, expected_exit,
):
    path = tmp_path / "campaign-send.db"
    Store(str(path)).close()
    monkeypatch.setattr(
        campaigns, "send_next_approved",
        lambda *_args, **_kwargs: {"ok": False, "sent": False, "code": code},
    )

    assert main(["--db", str(path), "campaign", "send-approved"]) == expected_exit
    assert code in capsys.readouterr().out


def test_campaign_cli_creates_and_lists_ranked_targets(tmp_path, capsys):
    path = tmp_path / "campaign-cli.db"

    assert main([
        "--db", str(path), "campaign", "create",
        "--name", "India security", "--count", "2",
    ]) == 0
    output = capsys.readouterr().out
    assert "created campaign:" in output and "India security" in output

    store = Store(str(path))
    values = store.outreach_campaigns()
    assert len(values) == 1 and values[0]["requested_count"] == 2
    assert len(store.outreach_campaign_targets(values[0]["id"])) == 2
    store.close()

    assert main(["--db", str(path), "campaign", "list"]) == 0
    listed = capsys.readouterr().out
    assert values[0]["id"] in listed and "ranked=2" in listed

    assert main(["--db", str(path), "campaign", "replies"]) == 0
    assert "0 replied, 0 opted out" in capsys.readouterr().out


def test_campaign_cli_requires_confirmation_to_delete_draft(tmp_path, capsys):
    path = tmp_path / "campaign-delete.db"
    with Store(str(path)) as store:
        campaign = store.create_outreach_campaign("Disposable", 1)
        store.upsert_outreach_campaign_target(campaign["id"], "Acme", "acme")

    command = [
        "--db", str(path), "campaign", "delete", "--campaign-id", campaign["id"],
    ]
    assert main(command) == 1
    assert "without --yes" in capsys.readouterr().err
    assert main([*command, "--yes"]) == 0
    assert f"deleted {campaign['id']}" in capsys.readouterr().out
    with Store(str(path)) as store:
        assert store.get_outreach_campaign(campaign["id"]) is None


def test_campaign_cli_builds_application_followup_queue(tmp_path, capsys):
    path = tmp_path / "campaign-followups.db"
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Jane\n", encoding="utf-8")
    with Store(str(path)) as store:
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

    assert main([
        "--db", str(path), "campaign", "followups",
        "--name", "Application follow-ups", "--count", "10",
    ]) == 0
    output = capsys.readouterr().out
    assert "Application follow-ups" in output
    assert "[application] recruiter@acme.example" in output

def test_campaign_cli_discovers_a_batch_when_no_target_is_named(tmp_path, capsys, monkeypatch):
    """Nine targets parked at needs_contact should not mean nine lookups by hand. The
    bounded batch the web button uses already exists; it was simply unreachable from a
    terminal, because discover always demanded one target id."""
    path = tmp_path / "campaign-discover.db"
    assert main([
        "--db", str(path), "campaign", "create", "--name", "batch", "--count", "3",
    ]) == 0
    capsys.readouterr()

    with Store(str(path)) as store:
        campaign_id = store.outreach_campaigns()[0]["id"]

    seen = {}

    def fake_batch(_cfg, _store, campaign, *, limit=5, fetch=True):
        seen.update(campaign=campaign, limit=limit, fetch=fetch)
        return {"ok": True, "processed": 3, "drafted": 1,
                "needs_contact": 2, "failed": 0, "remaining": 0}

    monkeypatch.setattr(campaigns, "discover_pending_targets", fake_batch)

    assert main([
        "--db", str(path), "campaign", "discover",
        "--campaign-id", campaign_id, "--no-fetch",
    ]) == 0

    # --no-fetch has to reach the batch, or an offline run quietly hits the network
    assert seen == {"campaign": campaign_id, "limit": 5, "fetch": False}
    out = capsys.readouterr().out
    assert "1 drafted" in out
    assert "2 still need a contact" in out


def test_campaign_cli_still_discovers_one_named_target(tmp_path, capsys, monkeypatch):
    """Regression guard: the batch branch now sits in front of this path, and the CLI
    side of single-target discovery had no test of its own."""
    path = tmp_path / "campaign-one.db"
    Store(str(path)).close()
    seen = {}

    def fake_single(_cfg, _store, target_id, *, force=False, fetch=True):
        seen.update(target_id=target_id, force=force, fetch=fetch)
        return {"company": "Cognite", "state": "draft",
                "selected_email": "recruiter@cognite.example", "leads": []}

    monkeypatch.setattr(campaigns, "discover_target", fake_single)

    assert main([
        "--db", str(path), "campaign", "discover",
        "--target-id", "target:one", "--no-fetch",
    ]) == 0

    assert seen == {"target_id": "target:one", "force": False, "fetch": False}
    assert "Cognite" in capsys.readouterr().out


def test_campaign_cli_batch_hands_back_where_to_look(tmp_path, capsys, monkeypatch):
    """The batch computed sourcing leads and dropped them, so a run reported "still
    need a contact" without saying what to do about it -- the opposite of what
    _sourcing_leads exists for."""
    path = tmp_path / "campaign-leads.db"
    assert main([
        "--db", str(path), "campaign", "create", "--name", "leads", "--count", "1",
    ]) == 0
    capsys.readouterr()

    with Store(str(path)) as store:
        campaign_id = store.outreach_campaigns()[0]["id"]
        # the label comes from the stored target, not from whatever discovery returned
        company = store.outreach_campaign_targets(campaign_id)[0]["company"]

    def fake_target(_cfg, _store, target_id, *, force=False, fetch=True):
        return {
            "id": target_id, "state": "needs_contact", "selected_email": "",
            "leads": [{
                "name": "Find a recruiter on LinkedIn", "title": "Recruiter",
                "source": "linkedin", "url": "https://example.invalid/recruiter",
            }],
        }

    monkeypatch.setattr(campaigns, "discover_target", fake_target)

    assert main([
        "--db", str(path), "campaign", "discover", "--campaign-id", campaign_id,
    ]) == 0

    out = capsys.readouterr().out
    assert "1 still need a contact" in out
    assert company in out
    assert "https://example.invalid/recruiter" in out
def test_campaign_cli_names_the_unknown_id(tmp_path, capsys):
    """A bare KeyError repr prints just the quoted key, which reads as a malformed
    command rather than a wrong id -- it cost two failed runs to tell the difference."""
    path = tmp_path / "campaign-unknown.db"
    Store(str(path)).close()

    assert main([
        "--db", str(path), "campaign", "discover",
        "--campaign-id", "campaign:nope", "--no-fetch",
    ]) == 2

    err = capsys.readouterr().err
    assert "no campaign or target with id" in err
    assert "campaign:nope" in err



def test_campaign_cli_batch_accepts_a_larger_limit(tmp_path, capsys, monkeypatch):
    """Nine stalled targets took two runs because the batch always used the default
    five, even though discover_pending_targets already accepts 1-10."""
    path = tmp_path / "campaign-limit.db"
    assert main([
        "--db", str(path), "campaign", "create", "--name", "limit", "--count", "2",
    ]) == 0
    capsys.readouterr()

    with Store(str(path)) as store:
        campaign_id = store.outreach_campaigns()[0]["id"]

    seen = {}

    def fake_batch(_cfg, _store, campaign, *, limit=5, fetch=True):
        seen.update(campaign=campaign, limit=limit, fetch=fetch)
        return {"ok": True, "processed": 2, "drafted": 0, "needs_contact": 2,
                "failed": 0, "remaining": 0, "leads": []}

    monkeypatch.setattr(campaigns, "discover_pending_targets", fake_batch)

    assert main([
        "--db", str(path), "campaign", "discover", "--campaign-id", campaign_id,
        "--limit", "9", "--no-fetch",
    ]) == 0

    assert seen["limit"] == 9


@pytest.mark.parametrize("limit", ["0", "99"])
def test_campaign_cli_refuses_a_batch_limit_out_of_range(tmp_path, capsys, limit):
    """Guard: the 1-10 bound lives inside discover_pending_targets, and --limit now
    exposes it to users. Clamping it in the CLI instead would silently shrink a batch
    and hide the refusal."""
    path = tmp_path / "campaign-limit-range.db"
    assert main([
        "--db", str(path), "campaign", "create", "--name", "range", "--count", "1",
    ]) == 0
    capsys.readouterr()

    with Store(str(path)) as store:
        campaign_id = store.outreach_campaigns()[0]["id"]

    assert main([
        "--db", str(path), "campaign", "discover", "--campaign-id", campaign_id,
        "--limit", limit, "--no-fetch",
    ]) == 2

    assert "between 1 and 10" in capsys.readouterr().err


def test_campaign_cli_tick_reports_the_work_that_is_due(tmp_path, capsys, monkeypatch):
    """tick already counts due work and the hourly task already runs it, but the count
    never reached the terminal, so a queue building up looked exactly like an idle one."""
    path = tmp_path / "campaign-tick.db"
    with Store(str(path)) as store:
        campaign = store.create_outreach_campaign("Due work", 1)
        store.set_outreach_campaign_status(campaign["id"], "active")
        store.upsert_outreach_campaign_target(campaign["id"], "Acme", "acme")
        target_id = store.outreach_campaign_targets(campaign["id"])[0]["id"]
        store.set_outreach_campaign_draft(
            target_id, selected_email="recruiter@acme.example",
            subject="Hello", body="Body",
        )
        store.set_outreach_campaign_policy(target_id, {"reviewed": True})
        store.approve_outreach_campaign_target(target_id)
        store.schedule_outreach_campaign_target(target_id, "2020-01-01T00:00:00Z")

    monkeypatch.setattr(campaigns, "sync_replies", lambda *_args, **_kwargs: {
        "ok": True, "inbox_status": "ok", "pending": 0, "replied": 0, "opted_out": 0,
    })

    assert main(["--db", str(path), "campaign", "tick"]) == 0
    assert "1 due" in capsys.readouterr().out


def test_campaign_cli_tick_no_fetch_skips_inbox_access(tmp_path, capsys, monkeypatch):
    from jobscope.ingest import inbox

    path = tmp_path / "campaign-tick-no-fetch.db"
    config = tmp_path / "config.json"
    config.write_text(
        '{"inbox":{"enabled":true,"accounts":[{"email":"me@example.com"}]}}',
        encoding="utf-8",
    )
    with Store(str(path)) as store:
        campaign = store.create_outreach_campaign("Replies", 1)
        target = store.upsert_outreach_campaign_target(
            campaign["id"], "Acme", "acme",
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email="recruiter@acme.example",
            subject="Hello", body="Body",
        )
        store.set_outreach_campaign_policy(target["id"], {"reviewed": True})
        approved = store.approve_outreach_campaign_target(target["id"])
        assert store.claim_outreach_campaign_target_send(
            target["id"], expected_approval_hash=approved["approval_hash"],
        )
        store.mark_outreach_campaign_target_sent(target["id"])

    calls = []
    monkeypatch.setattr(inbox, "run", lambda *_args, **_kwargs: calls.append("inbox") or 0)

    assert main([
        "--config", str(config), "--db", str(path),
        "campaign", "tick", "--no-fetch",
    ]) == 1
    assert calls == []
    assert "inbox not_fetched" in capsys.readouterr().out
