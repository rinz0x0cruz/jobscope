import contextlib
import os
import shutil
import tempfile

from jobscope.analyze.resume import import_resume_upload, parse_resume
from jobscope.core.config import load_config
from jobscope.core.store import Store

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "resume.md")


@contextlib.contextmanager
def _tmp_cfg_store():
    tmp = tempfile.mkdtemp()
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
    store = Store(cfg["output"]["db_path"])
    try:
        yield cfg, store, tmp
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)   # Windows may briefly hold the db handle



def test_parse_markdown_resume_contact():
    r = parse_resume(FIX)
    assert r.full_name == "Jane Doe"
    assert r.email == "jane.doe@example.com"
    assert "linkedin" in r.links and "github" in r.links


def test_parse_markdown_resume_skills():
    r = parse_resume(FIX)
    low = [s.lower() for s in r.skills]
    for expected in ("python", "aws", "kubernetes", "threat modeling", "iam"):
        assert expected in low, f"missing skill {expected} in {low}"


def test_parse_markdown_seniority_and_years():
    r = parse_resume(FIX)
    assert r.seniority == "senior"
    assert r.years_experience >= 6  # 2016 -> present


# --- résumé upload (dashboard, local serve) ---------------------------------
def test_import_resume_upload_stores_locally_and_imports():
    data = open(FIX, "rb").read()
    with _tmp_cfg_store() as (cfg, store, tmp):
        res = import_resume_upload(data, "Jane R\u00e9sum\u00e9.md", "default", store, cfg)
        assert res["ok"] and res["name"] == "default"
        assert os.path.exists(os.path.join(tmp, "resumes", "default.md"))   # stored locally
        assert store.get_resume() is not None                               # imported
        assert res["profile"] and res["profile"]["seniority"] == "senior"   # profile for the UI


def test_import_resume_upload_rejects_unsupported_type():
    with _tmp_cfg_store() as (cfg, store, _tmp):
        res = import_resume_upload(b"MZ...", "resume.exe", "default", store, cfg)
        assert not res["ok"] and "unsupported" in res["error"]
        assert store.get_resume() is None


def test_import_resume_upload_rejects_oversized():
    with _tmp_cfg_store() as (cfg, store, _tmp):
        res = import_resume_upload(b"x" * (5 * 1024 * 1024 + 1), "resume.md", "default", store, cfg)
        assert not res["ok"] and "too large" in res["error"]


def test_import_resume_upload_name_is_path_safe():
    data = open(FIX, "rb").read()
    with _tmp_cfg_store() as (cfg, store, tmp):
        res = import_resume_upload(data, "resume.md", "../../evil name", store, cfg)
        assert res["ok"]
        assert ".." not in res["name"] and "/" not in res["name"] and " " not in res["name"]
        # the file stays inside data/resumes/ regardless of the requested name
        assert os.path.exists(os.path.join(tmp, "resumes", f"{res['name']}.md"))
