"""Tests for the résumé-derived search profile (`analyze.profile`). Deterministic."""
import os
import tempfile

from jobscope.analyze import profile
from jobscope.core.config import load_config
from jobscope.core.model import Resume
from jobscope.core.store import Store


def _cfg(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
    return cfg


def _resume(**over) -> Resume:
    base = dict(
        full_name="Jane Doe", location="Bengaluru, India",
        skills=["python", "aws", "application security", "detection", "incident response"],
        titles=["Security Researcher Intern"], seniority="junior", years_experience=1.7)
    base.update(over)
    return Resume(**base)


def test_broaden_title_strips_seniority():
    assert profile._broaden_title("Senior Security Engineer") == "Security Engineer"
    assert profile._broaden_title("Security Researcher Intern") == "Security Researcher"
    assert profile._broaden_title("Staff Software Engineer") == "Software Engineer"
    assert profile._broaden_title("Lead Data Engineer") == "Data Engineer"


def test_derive_terms_from_titles_and_skills():
    terms = profile._derive_terms(_resume())
    assert "Security Researcher" in terms                 # broadened résumé title
    assert "Application Security Engineer" in terms        # appsec skill hint
    assert "Detection Engineer" in terms                   # detection skill hint
    assert len(terms) <= 6                                 # capped


def test_derive_terms_fallback_when_nothing_matches():
    terms = profile._derive_terms(_resume(titles=[], skills=["basket weaving"]))
    assert terms == ["Software Engineer"]


def test_build_profile_shape_and_locations():
    cfg = load_config(None)
    prof = profile.build_profile(_resume(), cfg, "research")
    assert prof["resume"] == "research"
    assert prof["seniority"] == "junior" and prof["years_experience"] == 1.7
    assert prof["search_terms"] and prof["locations"][0] == "Remote"
    assert "Bengaluru, India" in prof["locations"]
    assert prof["remote"] is True and prof["top_skills"]


def test_write_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        prof = profile.build_profile(_resume(), cfg, "research")
        profile.write_profile(profile._profile_path(cfg), prof)
        loaded = profile.load(cfg)
        assert loaded["search_terms"] == prof["search_terms"]
        assert loaded["locations"] == prof["locations"]
        assert loaded["resume"] == "research" and loaded["remote"] is True


def test_load_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert profile.load(_cfg(tmp)) is None


def test_apply_to_search_overlays_and_respects_empty():
    base = {"terms": ["software engineer"], "location": "Remote", "is_remote": True, "profiles": []}
    prof = {"search_terms": ["Security Engineer", "AppSec"],
            "locations": ["Remote", "Bengaluru"], "remote": False}
    s = profile.apply_to_search(base, prof)
    assert s["terms"] == ["Security Engineer", "AppSec"]
    assert s["profiles"] == [{"name": "Remote", "location": "Remote"},
                             {"name": "Bengaluru", "location": "Bengaluru"}]
    assert s["is_remote"] is False
    # empty profile fields never clobber the config values
    s2 = profile.apply_to_search(base, {"search_terms": [], "locations": []})
    assert s2["terms"] == ["software engineer"]


def test_ensure_seeded_only_once():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        p1 = profile.ensure_seeded(cfg, _resume(), "research")
        assert p1 and os.path.exists(p1)
        before = open(p1, encoding="utf-8").read()
        p2 = profile.ensure_seeded(cfg, _resume(skills=["go"]), "research")  # different résumé
        assert p2 is None                                  # already exists -> no reseed
        assert open(p1, encoding="utf-8").read() == before  # edits preserved


def test_run_build_show_force_and_errors():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        assert profile.run(cfg, store, action="build") == 1  # no résumé yet
        store.save_resume(_resume(), name="research")
        assert profile.run(cfg, store, action="build") == 0  # creates
        path = profile._profile_path(cfg)
        first = open(path, encoding="utf-8").read()
        assert profile.run(cfg, store, action="build") == 0  # exists, no --force
        assert open(path, encoding="utf-8").read() == first  # not clobbered
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n# my edit\n")
        assert profile.run(cfg, store, action="build", force=True) == 0  # overwrites
        assert "# my edit" not in open(path, encoding="utf-8").read()
        assert profile.run(cfg, store, action="show") == 0
        store.close()


def test_multi_profile_build_list_and_switch():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        store.save_resume(_resume(), name="research")
        store.save_resume(_resume(titles=["Security Consultant"]), name="consulting")
        assert profile.run(cfg, store, action="build", resume_name="research") == 0
        assert profile.run(cfg, store, action="build", resume_name="consulting") == 0
        names = profile.list_profiles(cfg)
        assert "research" in names and "consulting" in names and len(names) >= 2
        # the first profile built stays active until you switch
        assert profile.active_name(cfg) == "research"
        assert profile.load(cfg)["resume"] == "research"
        # switching changes what scan/load see
        assert profile.run(cfg, store, action="use", name="consulting") == 0
        assert profile.active_name(cfg) == "consulting"
        assert profile.load(cfg)["resume"] == "consulting"
        # an unknown name fails and leaves the active profile unchanged
        assert profile.run(cfg, store, action="use", name="nope") == 1
        assert profile.active_name(cfg) == "consulting"
        # listing works and building a 3rd keeps the others
        assert profile.run(cfg, store, action="list") == 0
        store.close()


def test_ensure_seeded_multiple_names_keeps_first_active():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        p1 = profile.ensure_seeded(cfg, _resume(), "research")
        p2 = profile.ensure_seeded(cfg, _resume(titles=["Security Consultant"]), "consulting")
        assert p1 and p2 and p1 != p2
        assert set(profile.list_profiles(cfg)) == {"research", "consulting"}
        assert profile.active_name(cfg) == "research"       # first seeded is active


def test_legacy_single_profile_migrates_into_store():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        # simulate a pre-multi-profile install: one data/profile.yaml
        legacy = profile._legacy_path(cfg)
        os.makedirs(os.path.dirname(legacy), exist_ok=True)
        profile.write_profile(legacy, profile.build_profile(_resume(), cfg, "research"))
        assert os.path.exists(legacy)
        # first access migrates it into profiles/research.yaml and makes it active
        loaded = profile.load(cfg)
        assert loaded is not None and loaded["resume"] == "research"
        assert not os.path.exists(legacy)                   # moved, not copied
        assert profile.list_profiles(cfg) == ["research"]
        assert profile.active_name(cfg) == "research"
