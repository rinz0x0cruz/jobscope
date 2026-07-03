"""Integration: the AI ``discipline`` hint breaks the resume-routing tie for a
lean-AMBIGUOUS posting, and is a strict no-op when AI is off (routing stays the
deterministic best-fit). ai.chat / ai.available are monkeypatched -- no network."""
from jobscope import ai, match
from jobscope.config import load_config
from jobscope.model import Job, Resume
from jobscope.store import Store


def _technical_resume() -> Resume:
    # all-technical skills -> _resume_lean == +1 (the "most technical" framing)
    return Resume(
        full_name="Tech Cand",
        skills=["reverse engineering", "malware", "ghidra", "shellcode", "exploit", "fuzzing"],
        titles=["Cybersecurity Analyst"],
        seniority="mid",
        location="Remote",
    )


def _advisory_resume() -> Resume:
    # all-advisory skills -> _resume_lean == -1 (the "most advisory" framing)
    return Resume(
        full_name="Advisory Cand",
        skills=["grc", "audit", "compliance", "soc 2", "iso 27001", "governance"],
        titles=["Cybersecurity Analyst"],
        seniority="mid",
        location="Remote",
    )


def _ambiguous_job(url: str) -> Job:
    # 3 technical + 4 advisory signal words in the body, none in the (neutral) title,
    # and no seniority/years cue -> |_job_lean| < 0.25 (ambiguous) AND it reaches the
    # AI tie-break bucket. The advisory resume matches one more skill, so the
    # deterministic best-fit route is the advisory resume.
    desc = ("We are hiring a cybersecurity analyst to support our team. Responsibilities "
            "span malware triage, ghidra usage, and shellcode analysis alongside grc, audit, "
            "compliance, and soc 2 activities. This hybrid role blends day-to-day operations "
            "with documentation, reporting, and collaboration across teams to keep the "
            "program healthy and effective.")
    return Job(source="indeed", title="Cybersecurity Analyst", company="Acme", url=url,
               is_remote=True, salary_min=140000, salary_max=180000, description=desc).ensure_id()


def _cfg(db):
    cfg = load_config(None)
    cfg["output"]["db_path"] = db
    cfg["match"]["ai_seniority_tiebreak"] = True
    cfg["ai"]["enabled"] = True
    return cfg


def _seeded_store(db):
    store = Store(db)
    store.save_resume(_technical_resume(), name="technical")
    store.save_resume(_advisory_resume(), name="advisory")
    return store


def test_ai_discipline_flips_ambiguous_route_to_technical(monkeypatch, tmp_path):
    db = str(tmp_path / "route.db")
    store = _seeded_store(db)
    job = _ambiguous_job("r1")
    store.upsert_job(job)

    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "chat", lambda *a, **k:
                        '{"level":"mid","required_years":4,"discipline":"technical"}')

    match.run(_cfg(db), store)

    j = store.get_job(job.id)
    # deterministic best-fit would route to "advisory"; the AI discipline overrides it
    assert j.resume_base == "technical"
    assert "AI-route:technical" in (j.rationale or "")


def test_ai_discipline_advisory_route(monkeypatch, tmp_path):
    db = str(tmp_path / "route2.db")
    store = _seeded_store(db)
    job = _ambiguous_job("r2")
    store.upsert_job(job)

    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "chat", lambda *a, **k:
                        '{"level":"mid","required_years":4,"discipline":"advisory"}')

    match.run(_cfg(db), store)

    j = store.get_job(job.id)
    assert j.resume_base == "advisory"
    assert "AI-route:advisory" in (j.rationale or "")


def test_routing_deterministic_when_ai_off(monkeypatch, tmp_path):
    db = str(tmp_path / "route_off.db")
    store = _seeded_store(db)
    job = _ambiguous_job("r3")
    store.upsert_job(job)

    monkeypatch.setattr(ai, "available", lambda cfg: False)
    called = []
    monkeypatch.setattr(ai, "chat", lambda *a, **k: called.append(1) or None)

    match.run(_cfg(db), store)

    j = store.get_job(job.id)
    assert not called                            # classifier never consulted
    assert j.resume_base == "advisory"           # unchanged deterministic best-fit route
    assert "AI-route" not in (j.rationale or "")
