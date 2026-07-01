"""Tests for filters (clearance/sponsorship/block-list/age) and multi-resume select."""
import os
import tempfile

from jobscope import match
from jobscope.config import load_config
from jobscope.model import Job, Resume
from jobscope.store import Store


def _mcfg(**over):
    c = load_config(None)
    f = c["filters"]
    f.update(over)
    return c


def _job(desc="", title="Security Engineer", company="Acme", url="u1", date_posted=""):
    return Job(source="indeed", title=title, company=company, url=url,
               description=desc, is_remote=True, date_posted=date_posted).ensure_id()


def test_clearance_and_sponsorship_detection():
    assert match.clearance_flags(_job(desc="Active TS/SCI security clearance required"))
    assert match.clearance_flags(_job(desc="Must be a US citizen"))
    assert not match.clearance_flags(_job(desc="python aws remote"))
    assert match.no_sponsorship(_job(desc="We are unable to sponsor visas at this time"))
    assert not match.no_sponsorship(_job(desc="great benefits, remote"))


def test_apply_filters_blocklist():
    f = _mcfg(block_companies=["Acme"])["filters"]
    assert match.apply_filters(_job(company="Acme Corp"), f)
    f = _mcfg(block_title_keywords=["senior"])["filters"]
    assert match.apply_filters(_job(title="Senior Security Engineer"), f)
    f = _mcfg(block_keywords=["clearance"])["filters"]
    assert match.apply_filters(_job(desc="requires clearance"), f)
    assert match.apply_filters(_job(desc="normal role"), _mcfg()["filters"]) is None


def test_apply_filters_clearance_and_sponsorship():
    f = _mcfg(exclude_clearance=True)["filters"]
    assert "clearance" in (match.apply_filters(_job(desc="Top Secret clearance required"), f) or "")
    f = _mcfg(needs_sponsorship=True)["filters"]
    assert "sponsor" in (match.apply_filters(_job(desc="No visa sponsorship provided"), f) or "")


def test_apply_filters_age():
    f = _mcfg(max_age_days=30)["filters"]
    assert match.apply_filters(_job(date_posted="2000-01-01"), f)          # ancient -> blocked
    assert match.apply_filters(_job(date_posted=""), f) is None            # unknown -> keep


def test_match_run_forces_skip_on_filter():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _mcfg(exclude_clearance=True)
        cfg["output"]["db_path"] = os.path.join(tmp, "f.db")
        store = Store(cfg["output"]["db_path"])
        store.save_resume(Resume(skills=["python", "aws", "iam"], seniority="mid",
                                 titles=["Security Engineer"]))
        good = _job(desc="python aws iam " * 10, url="g")
        cleared = _job(desc="python aws iam " * 10 + " active security clearance required", url="c")
        store.upsert_job(good)
        store.upsert_job(cleared)
        match.run(cfg, store)
        assert store.get_job(cleared.id).tier == "Skip"
        assert "⛔" in store.get_job(cleared.id).rationale
        store.close()


def test_multi_resume_selects_best_base():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "m.db")
        store = Store(cfg["output"]["db_path"])
        store.save_resume(Resume(skills=["reverse engineering", "malware analysis", "yara"],
                                 seniority="mid", titles=["Security Researcher"]), name="research")
        store.save_resume(Resume(skills=["pci dss", "iso 27001", "compliance", "audit"],
                                 seniority="mid", titles=["Security Consultant"]), name="consulting")
        re_job = _job(desc="reverse engineering malware analysis yara " * 6,
                      title="Malware Researcher", url="r")
        grc_job = _job(desc="pci dss iso 27001 compliance audit " * 6,
                       title="GRC Consultant", url="g")
        store.upsert_job(re_job)
        store.upsert_job(grc_job)
        match.run(cfg, store)
        assert store.get_job(re_job.id).resume_base == "research"
        assert store.get_job(grc_job.id).resume_base == "consulting"
        store.close()


def test_company_quality_tiers():
    from jobscope.companies import company_quality
    assert company_quality("Google")[0] == 1.0
    assert company_quality("Meta Platforms, Inc.")[0] == 1.0      # token subset
    assert company_quality("Palo Alto Networks")[0] == 0.90
    assert company_quality("Metabase")[0] == 0.5                  # not "meta"
    assert company_quality("Some Random Startup LLC")[0] == 0.5


def test_company_score_prefers_user_list_then_curated():
    cfg = _mcfg()["match"]
    cfg["prefer_companies"] = ["acme"]
    assert match._company_score(_job(company="Acme Corp"), cfg) == (1.0, "preferred")
    s, label = match._company_score(_job(company="Nvidia"), {"prefer_companies": []})
    assert s == 1.0 and label == "elite"


def test_company_boosts_ranking():
    r = Resume(skills=["python", "aws"], seniority="mid", titles=["Security Engineer"])
    cfg = _mcfg()["match"]
    cfg["want_remote"] = True
    famous = _job(company="Google", desc="python aws " * 8)
    nobody = _job(company="Obscure Widgets LLC", desc="python aws " * 8)
    s_famous, _, _ = match.score_job(famous, r, cfg)
    s_nobody, _, _ = match.score_job(nobody, r, cfg)
    assert s_famous > s_nobody


def test_prefer_locations_boost():
    r = Resume(skills=["python"], location="Berlin")
    j = Job(title="x", company="c", location="Bengaluru, India", is_remote=False)
    assert match._location_score(r, j, True, ["Bengaluru"]) == 1.0
    assert match._location_score(r, j, True, []) < 1.0             # without preference, weaker


def test_company_size_bands():
    from jobscope.companies import company_size
    assert company_size("Amazon")[1] == "mega"
    assert company_size("Wiz")[1] == "small"
    assert company_size("Mistral AI")[1] == "startup"
    assert company_size("Totally Unknown Co") == (0.5, "")        # neutral, no band


def test_prefer_company_size_direction():
    big = match._company_score(_job(company="Amazon"), {"prefer_company_size": "large"})[0]
    small = match._company_score(_job(company="Amazon"), {"prefer_company_size": "small"})[0]
    assert big > small                                            # mega scores high when preferring large
    # a company with no size data is unaffected (prestige-only fallback)
    assert match._company_score(_job(company="Obscure Widgets LLC"),
                                {"prefer_company_size": "large"})[0] == 0.5


def test_company_size_shifts_ranking():
    r = Resume(skills=["python", "aws"], seniority="mid", titles=["Security Engineer"])
    cfg = _mcfg()["match"]
    cfg["prefer_company_size"] = "large"
    cfg["want_remote"] = True
    mega = _job(company="Amazon", desc="python aws " * 8)
    tiny = _job(company="Mistral", desc="python aws " * 8)
    assert match.score_job(mega, r, cfg)[0] > match.score_job(tiny, r, cfg)[0]
