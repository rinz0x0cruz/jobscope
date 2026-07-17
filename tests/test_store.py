import os
import tempfile

from jobscope.core.model import Application, Job, Resume
from jobscope.core.store import Store


def _store():
    tmp = tempfile.mkdtemp()
    return Store(os.path.join(tmp, "t.db"))


def test_upsert_and_dedupe():
    store = _store()
    j = Job(source="indeed", title="Security Engineer", company="Acme",
            url="https://x/1").ensure_id()
    assert store.upsert_job(j) is True     # first insert
    assert store.upsert_job(j) is False    # dedupe on second
    assert len(store.jobs()) == 1
    store.close()


def test_score_persist_and_order():
    store = _store()
    a = Job(source="s", title="A", company="A", url="u1").ensure_id()
    b = Job(source="s", title="B", company="B", url="u2").ensure_id()
    store.upsert_job(a)
    store.upsert_job(b)
    store.update_score(a.id, 90.0, "Strong", "top")
    store.update_score(b.id, 40.0, "Stretch", "meh")
    ranked = store.jobs(order_by_score=True)
    assert ranked[0].id == a.id and ranked[0].tier == "Strong"
    store.close()


def test_resume_and_enrichment_roundtrip():
    store = _store()
    store.save_resume(Resume(full_name="Mohit", skills=["python"], seniority="senior"))
    assert store.get_resume().full_name == "Mohit"
    store.save_enrichment("Acme", comp={"min": 100000, "max": 150000})
    store.save_enrichment("Acme", stock={"ticker": "ACME"})  # merge, don't clobber
    enr = store.get_enrichment("Acme")
    assert enr["comp"]["max"] == 150000
    assert enr["stock"]["ticker"] == "ACME"
    store.close()


def test_application_tracking():
    store = _store()
    j = Job(source="s", title="A", company="Acme", url="u1").ensure_id()
    store.upsert_job(j)
    store.set_application(Application(job_id=j.id, status="prepared"))
    store.set_application(Application(job_id=j.id, status="applied"))
    apps = store.applications()
    assert len(apps) == 1 and apps[0]["status"] == "applied"
    assert apps[0]["company"] == "Acme"
    store.close()


def test_offer_tracking():
    store = _store()
    j = Job(source="s", title="A", company="Acme", url="u1").ensure_id()
    store.upsert_job(j)
    store.set_application(Application(job_id=j.id, status="offer"))
    # set_offer upserts interview/offer fields without disturbing status
    store.set_offer(j.id, interview_at="2026-07-20 14:00",
                    salary_offered="$185k + 15%", offer_accepted="pending")
    app = store.get_application(j.id)
    assert app["status"] == "offer"
    assert app["interview_at"] == "2026-07-20 14:00"
    assert app["salary_offered"] == "$185k + 15%"
    assert app["offer_accepted"] == "pending"
    # empty values never clobber saved ones; a non-empty value overwrites
    store.set_offer(j.id, offer_accepted="accepted")
    app = store.get_application(j.id)
    assert app["offer_accepted"] == "accepted"
    assert app["salary_offered"] == "$185k + 15%"      # untouched
    # surfaced through applications() for the dashboard emit
    row = store.applications()[0]
    assert row["salary_offered"] == "$185k + 15%" and row["offer_accepted"] == "accepted"
    store.close()


def test_ai_cache():
    store = _store()
    assert store.ai_cache_get("missing") is None
    store.ai_cache_put("k", "model", "prompt", "resp")
    assert store.ai_cache_get("k") == "resp"
    assert store.conn.execute(
        "SELECT prompt FROM ai_cache WHERE key = 'k'"
    ).fetchone()["prompt"] == ""
    store.close()


def test_named_resumes_and_default():
    store = _store()
    store.save_resume(Resume(full_name="R", skills=["yara"]), name="research")
    store.save_resume(Resume(full_name="C", skills=["audit"]), name="consulting")
    names = {n for n, _ in store.list_resumes()}
    assert names == {"research", "consulting"}
    assert store.get_named_resume("research").full_name == "R"
    # get_resume() with no name returns a sensible primary
    assert store.get_resume() is not None
    store.save_resume(Resume(full_name="D"), name="default")
    assert store.get_resume().full_name == "D"      # prefers 'default'
    store.close()


def test_meta_roundtrip():
    store = _store()
    assert store.meta_get("last_review") is None
    assert store.meta_get("last_review", "x") == "x"
    store.meta_set("last_review", "2026-07-01T00:00:00Z")
    assert store.meta_get("last_review") == "2026-07-01T00:00:00Z"
    store.close()


def test_source_health_upserts_current_state():
    store = _store()
    store.set_source_health(
        "ats:Acme", provider="greenhouse", slug="acme", status="error",
        attempts=3, status_code=503, detail="temporary failure",
    )
    store.set_source_health(
        "ats:Acme", provider="greenhouse", slug="acme", status="ok",
        item_count=12, attempts=1, status_code=200,
    )

    rows = store.source_health("ats:Acme")

    assert len(rows) == 1
    assert rows[0]["status"] == "ok" and rows[0]["item_count"] == 12
    assert rows[0]["attempts"] == 1 and rows[0]["status_code"] == 200
    assert rows[0]["checked_at"]
    store.close()


def test_job_analysis_is_versioned_by_job_and_resume():
    store = _store()
    store.save_job_analysis(
        "job-1", resume_base="research", version=1,
        comp={"range": "$100k", "source": "posting"},
        brief={"text": "role one"},
    )
    store.save_job_analysis(
        "job-2", resume_base="consulting", version=1,
        comp={"range": "$200k", "source": "posting"},
        brief={"text": "role two"},
    )

    first = store.get_job_analysis("job-1", resume_base="research", version=1)
    second = store.get_job_analysis("job-2", resume_base="consulting", version=1)

    assert first["comp"]["range"] == "$100k" and first["brief"]["text"] == "role one"
    assert second["comp"]["range"] == "$200k" and second["brief"]["text"] == "role two"
    assert store.get_job_analysis("job-1", resume_base="consulting", version=1) == {}
    assert store.get_job_analysis("job-1", resume_base="research", version=2) == {}
    store.close()


def test_resume_base_persists():
    store = _store()
    j = Job(source="s", title="A", company="A", url="u1").ensure_id()
    store.upsert_job(j)
    store.update_score(j.id, 80, "Strong", "x", resume_base="research")
    assert store.get_job(j.id).resume_base == "research"
    store.close()


def test_remote_scope_and_raw_flag_roundtrip():
    store = _store()
    # JobSpy-style job: geo-restricted remote with a preserved raw flag
    j = Job(source="indeed", title="Detection Engineer", company="Acme",
            url="https://x/ie", is_remote=True, remote_scope="Ireland",
            raw_is_remote=True).ensure_id()
    store.upsert_job(j)
    got = store.get_job(j.id)
    assert got.remote_scope == "Ireland"
    assert got.raw_is_remote is True
    listed = {x.id: x for x in store.jobs()}[j.id]     # also survives via jobs()
    assert listed.remote_scope == "Ireland" and listed.raw_is_remote is True
    # ATS-style job: raw flag absent -> stays None; global scope round-trips
    k = Job(source="ats", title="AppSec", company="Beta", url="https://x/none",
            is_remote=True, remote_scope="global", raw_is_remote=None).ensure_id()
    store.upsert_job(k)
    got_k = store.get_job(k.id)
    assert got_k.raw_is_remote is None
    assert got_k.remote_scope == "global"
    store.close()

