"""Public (redacted) dashboard mode.

Private fields (third-party referral contacts, the application funnel, search
terms, and score rationale) must never reach a publicly-hosted dashboard, while
public job info and fit scores are kept. Fully offline -- no network.
"""
import os
import tempfile

from jobscope.deliver import render
from jobscope.core.config import load_config
from jobscope.core.model import Application, Contact, Job
from jobscope.core.store import Store


def _seed(store):
    job = Job(source="indeed", title="Senior Security Engineer", company="Acme",
              url="https://jobs.example/acme-sse", is_remote=True,
              score=82.0, tier="Strong", resume_base="research",
              rationale="Strong overlap; ~1.7y experience (junior)").ensure_id()
    store.upsert_job(job)
    store.save_contacts([Contact(
        id="c1", company="Acme", name="Dana Recruiter", title="Talent Partner",
        source="team-page", profile_url="https://linkedin.com/in/dana-secret")])
    store.set_application(Application(job_id=job.id, status="applied"))
    return job


def test_public_mode_redacts_sensitive_fields():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        cfg["output"]["public_dashboard_path"] = os.path.join(tmp, "public.html")
        cfg["search"]["terms"] = ["threat detection engineer"]

        store = Store(cfg["output"]["db_path"])
        _seed(store)

        # Full (local) dashboard embeds everything.
        full = open(render.build(cfg, store), encoding="utf-8").read()
        assert "Dana Recruiter" in full
        assert "dana-secret" in full
        assert "threat detection engineer" in full
        assert "1.7y experience" in full

        # Public dashboard -> a separate file, with private fields stripped.
        pub_path = render.build(cfg, store, public=True)
        assert pub_path == cfg["output"]["public_dashboard_path"]
        pub = open(pub_path, encoding="utf-8").read()
        assert "Senior Security Engineer" in pub      # core public job info kept
        assert "Acme" in pub
        assert "Dana Recruiter" not in pub            # referral contact name gone
        assert "dana-secret" not in pub               # referral contact URL gone
        assert "threat detection engineer" not in pub  # search term gone
        assert "1.7y experience" not in pub           # score rationale gone

        store.close()


def test_redact_public_clears_private_keys():
    rows = [{
        "title": "X", "company": "Acme", "score": 82,
        "contacts": [{"name": "Dana", "url": "https://linkedin.com/in/dana"}],
        "rationale": "~1.7y experience (junior)", "base": "research",
    }]
    overview = {"funnel": {"applied": 3}, "targets": ["ml eng"], "gaps": [["k8s", 2]]}

    render._redact_public(rows, overview)

    assert rows[0]["contacts"] == []
    assert rows[0]["rationale"] == ""
    assert rows[0]["base"] == ""
    assert rows[0]["title"] == "X"        # public job info untouched
    assert rows[0]["score"] == 82
    assert overview["funnel"] == {}
    assert overview["targets"] == []
    assert overview["gaps"]               # aggregate skill gaps intentionally kept
