"""Write-once submission snapshots (issue #105 phase 1).

Application rows outlive the job rows they came from -- in the real database only 6
of 175 applications still join to a stored job -- so the context needed to learn from
an outcome has to be captured at the moment of applying, and never rewritten.
"""
import hashlib
import os
import tempfile

from jobscope.core.model import Application, Job
from jobscope.core.store import Store


def _job(**over):
    fields = dict(
        source="greenhouse", title="Security Analyst", company="Acme Security",
        url="https://boards.greenhouse.io/acme/jobs/1", description="siem python",
        location="Bengaluru, India", date_posted="2026-07-01",
    )
    fields.update(over)
    return Job(**fields).ensure_id()


def _store(tmp, name="snap.db"):
    return Store(os.path.join(tmp, name))


def _applied(job, **over):
    fields = dict(job_id=job.id, status="applied", company=job.company,
                  title=job.title, source=job.source, applied_at="2026-08-01T09:00:00Z")
    fields.update(over)
    return Application(**fields)


def test_applying_captures_the_job_context_once():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.update_score(job.id, 82.5, "Strong", "top: skills 90%", resume_base="research")

            store.set_application(_applied(job))

            snapshot = store.submission_snapshot(job.id)
            assert snapshot is not None
            assert snapshot["score"] == 82.5
            assert snapshot["tier"] == "Strong"
            assert snapshot["resume_base"] == "research"
            assert snapshot["source"] == "greenhouse"
            assert snapshot["company"] == "Acme Security"
            assert snapshot["url"] == job.url


def test_rescoring_the_job_never_rewrites_a_submitted_snapshot():
    """Re-running tailoring or a later match must not rewrite what was actually sent."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.update_score(job.id, 82.5, "Strong", "top: skills 90%", resume_base="research")
            store.set_application(_applied(job))

            store.update_score(job.id, 31.0, "Skip", "⛔ blocked", resume_base="consulting")
            store.set_application(_applied(job, status="interview"))

            snapshot = store.submission_snapshot(job.id)
            assert snapshot["score"] == 82.5
            assert snapshot["tier"] == "Strong"
            assert snapshot["resume_base"] == "research"


def test_context_survives_the_job_row_disappearing():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.update_score(job.id, 64.0, "Good", "top: skills 70%", resume_base="research")
            store.set_application(_applied(job))

            store.conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))
            store.conn.commit()

            assert store.get_job(job.id) is None
            snapshot = store.submission_snapshot(job.id)
            assert snapshot["tier"] == "Good"
            assert snapshot["title"] == "Security Analyst"


def test_resaving_a_historical_applied_row_does_not_backfill():
    """An hourly background tick re-saves long-applied rows. The spec says those stay
    unknown unless the user explicitly backfills, so a re-save must capture nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.conn.execute(
                "INSERT INTO applications (job_id, status, company, applied_at)"
                " VALUES (?, ?, ?, ?)",
                ("mail:historic", "applied", "Legacy Corp", "2026-01-01T00:00:00Z"),
            )
            store.conn.commit()
            assert store.submission_snapshot("mail:historic") is None

            store.set_application(Application(
                job_id="mail:historic", status="applied", company="Legacy Corp",
                applied_at="2026-01-01T00:00:00Z",
            ))

            assert store.submission_snapshot("mail:historic") is None


def test_the_snapshot_fingerprints_the_submitted_artifacts():
    """A path cannot prove the file was not re-tailored afterwards; a hash can."""
    with tempfile.TemporaryDirectory() as tmp:
        resume = os.path.join(tmp, "resume.pdf")
        with open(resume, "wb") as handle:
            handle.write(b"submitted resume bytes")
        expected = hashlib.sha256(b"submitted resume bytes").hexdigest()

        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.set_application(_applied(job, resume_path=resume))

            assert store.submission_snapshot(job.id)["resume_sha256"] == expected


def test_the_snapshot_fingerprints_the_submitted_cover_letter():
    with tempfile.TemporaryDirectory() as tmp:
        cover = os.path.join(tmp, "cover.md")
        with open(cover, "wb") as handle:
            handle.write(b"submitted cover bytes")
        expected = hashlib.sha256(b"submitted cover bytes").hexdigest()

        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.set_application(_applied(job, cover_path=cover))

            assert store.submission_snapshot(job.id)["cover_sha256"] == expected


def test_a_missing_artifact_records_no_fingerprint_rather_than_failing():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.set_application(_applied(job, resume_path=os.path.join(tmp, "gone.pdf")))

            assert store.submission_snapshot(job.id)["resume_sha256"] == ""


def test_statuses_before_applying_record_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            job = _job()
            store.upsert_job(job)
            store.set_application(Application(job_id=job.id, status="prepared"))

            assert store.submission_snapshot(job.id) is None


def test_an_application_with_no_stored_job_still_records_what_it_knows():
    """Inbox-only applications have no job row; the snapshot must not invent one."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:abc123", status="applied", company="Northwind",
                title="Detection Engineer", source="inbox", applied_at="2026-08-02T09:00:00Z",
            ))

            snapshot = store.submission_snapshot("mail:abc123")
            assert snapshot["company"] == "Northwind"
            assert snapshot["source"] == "inbox"
            assert snapshot["score"] is None
            assert snapshot["tier"] == ""
