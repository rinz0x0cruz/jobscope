import os
import tempfile

from jobscope.model import Application, Job, Resume
from jobscope.store import Store


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


def test_ai_cache():
    store = _store()
    assert store.ai_cache_get("missing") is None
    store.ai_cache_put("k", "model", "prompt", "resp")
    assert store.ai_cache_get("k") == "resp"
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


def test_resume_base_persists():
    store = _store()
    j = Job(source="s", title="A", company="A", url="u1").ensure_id()
    store.upsert_job(j)
    store.update_score(j.id, 80, "Strong", "x", resume_base="research")
    assert store.get_job(j.id).resume_base == "research"
    store.close()

