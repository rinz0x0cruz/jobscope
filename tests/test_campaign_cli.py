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