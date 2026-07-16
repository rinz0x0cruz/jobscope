"""Public dashboard mode = whole-app auth.

The public build must ship NO consumable data at all -- no rows, applications,
profile, funnel, or search terms. The un-redacted payload is only ever available
via the separately-built AES-256-GCM blob, decrypted in the browser with a
passphrase. Fully offline -- no network.
"""
import json
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


def test_public_mode_ships_no_data():
    """Whole-app auth: the public build must contain NO consumable data. Only the
    separately-built encrypted blob can reveal anything, and only with the
    passphrase."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["search"]["terms"] = ["threat detection engineer"]

        store = Store(cfg["output"]["db_path"])
        _seed(store)

        # Full (local) payload embeds everything.
        full = json.dumps(render.build_data(cfg, store, public=False), ensure_ascii=False)
        assert "Dana Recruiter" in full
        assert "dana-secret" in full
        assert "threat detection engineer" in full
        assert "1.7y experience" in full

        # Public payload -> an empty, schema-valid shell. Nothing consumable ships.
        pub = render.build_data(cfg, store, public=True)
        assert pub["rows"] == []
        assert pub["total"] == 0
        assert pub["applications"] == []
        assert pub["applied_outreach"] == []
        assert pub["companies"] == []
        assert pub["reviews"] == []
        assert pub["profile"] is None
        assert pub["overview"]["funnel"] == {}
        assert pub["overview"]["targets"] == []
        assert pub["overview"]["gaps"] == []

        # And none of the seeded private strings survive anywhere in the JSON.
        blob = json.dumps(pub, ensure_ascii=False)
        for secret in ("Senior Security Engineer", "Acme", "Dana Recruiter",
                       "dana-secret", "threat detection engineer", "1.7y experience"):
            assert secret not in blob

        store.close()
