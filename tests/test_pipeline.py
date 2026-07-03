"""Offline end-to-end: resume + synthetic jobs -> match -> dashboard.

Exercises the P1 pipeline without touching the network (no JobSpy), so CI can
validate the whole core loop.
"""
import os
import tempfile

from jobscope.analyze import match
from jobscope.deliver import render
from jobscope.core.config import load_config
from jobscope.core.model import Job
from jobscope.core.store import Store

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "resume.md")


def _seed(store):
    from jobscope.analyze.resume import parse_resume
    store.save_resume(parse_resume(FIX))
    jobs = [
        Job(source="indeed", title="Senior Security Engineer", company="Acme",
            url="u1", is_remote=True, salary_min=160000, salary_max=210000,
            description="python aws kubernetes iam threat modeling terraform sast dast " * 6),
        Job(source="linkedin", title="Security Analyst", company="Globex",
            url="u2", is_remote=False, location="Austin, TX",
            description="siem soc splunk incident response " * 6),
        Job(source="indeed", title="Retail Sales Associate", company="ShopCo",
            url="u3", description="cold calling quota crm upselling " * 6),
    ]
    for j in jobs:
        store.upsert_job(j.ensure_id())


def test_pipeline_ranks_and_renders():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e2e.db")
        cfg = load_config(None)
        cfg["output"]["db_path"] = db
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")

        store = Store(db)
        _seed(store)

        rc = match.run(cfg, store)
        assert rc == 0

        ranked = store.jobs(order_by_score=True)
        assert ranked[0].company == "Acme"          # strongest fit on top
        assert ranked[-1].company == "ShopCo"        # sales role at the bottom
        assert ranked[0].score > ranked[-1].score

        path = render.build(cfg, store)
        html = open(path, encoding="utf-8").read()
        assert "Senior Security Engineer" in html
        assert "jobscope" in html
        # embedded data is valid + ordered by score
        assert "Acme" in html and "ShopCo" in html
        store.close()


def test_match_requires_resume():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "n.db")
        store = Store(cfg["output"]["db_path"])
        assert match.run(cfg, store) == 1          # no resume -> friendly failure
        store.close()
