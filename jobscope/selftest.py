"""Offline self-tests for jobscope (no network, no API keys, no browser).

Mirrors threatscope/exploitrank `selftest`: a fast confidence check that the
deterministic core works on a fresh machine. Returns 0 on success, 1 on failure.
"""
from __future__ import annotations

import os
import tempfile


class _Check:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, name: str, cond: bool, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not cond:
            line += f"  ({detail})"
        print(line)
        if cond:
            self.passed += 1
        else:
            self.failed += 1


def run() -> int:
    c = _Check()

    # --- model ------------------------------------------------------------
    from .model import Job, job_id, slugify

    id1 = job_id("indeed", "Security Engineer", "Acme", "https://x/y")
    id2 = job_id("indeed", "Security Engineer", "Acme", "https://x/y")
    id3 = job_id("indeed", "Security Engineer", "Acme", "https://x/z")
    c.ok("job_id is deterministic", id1 == id2)
    c.ok("job_id varies by url", id1 != id3)
    c.ok("slugify is filesystem-safe", slugify("Foo Bar!/Baz") == "foo-bar-baz")
    j = Job(source="indeed", title="SE", company="Acme").ensure_id()
    c.ok("job.ensure_id fills id", bool(j.id))

    # --- config -----------------------------------------------------------
    from .config import DEFAULT_CONFIG, _deep_merge, load_config

    merged = _deep_merge(DEFAULT_CONFIG, {"search": {"location": "Berlin"}})
    c.ok("deep_merge overrides leaf", merged["search"]["location"] == "Berlin")
    c.ok("deep_merge keeps siblings", merged["search"]["results_wanted"] == 25)
    c.ok("default weights sum ~1.0",
         abs(sum(DEFAULT_CONFIG["match"]["weights"].values()) - 1.0) < 1e-9)
    cfg = load_config(None)
    c.ok("load_config returns defaults", cfg["ai"]["provider"] == "groq")

    # --- store ------------------------------------------------------------
    from .model import Application, Resume
    from .store import Store

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "t.db"))
        is_new = store.upsert_job(j)
        c.ok("upsert_job inserts", is_new)
        c.ok("upsert_job dedupes", store.upsert_job(j) is False)
        store.update_score(j.id, 82.0, "Strong", "great fit")
        got = store.get_job(j.id)
        c.ok("score persists", got is not None and got.tier == "Strong")

        r = Resume(full_name="Mohit", skills=["python", "iam"], seniority="senior")
        store.save_resume(r)
        c.ok("resume round-trips", (store.get_resume() or Resume()).full_name == "Mohit")

        store.save_enrichment("Acme", comp={"min": 100, "max": 150})
        c.ok("enrichment persists", store.get_enrichment("Acme")["comp"]["max"] == 150)

        store.set_application(Application(job_id=j.id, status="prepared"))
        c.ok("application persists", store.applications()[0]["status"] == "prepared")

        store.ai_cache_put("k", "m", "p", "resp")
        c.ok("ai cache round-trips", store.ai_cache_get("k") == "resp")
        store.close()

    # --- match (deterministic scoring) -----------------------------------
    try:
        from . import match  # noqa: F401
        _selftest_match(c)
    except ImportError:
        pass  # not yet built

    total = c.passed + c.failed
    print(f"\n  {c.passed}/{total} checks passed")
    return 0 if c.failed == 0 else 1


def _selftest_match(c: "_Check") -> None:
    from .match import score_job
    from .model import Job, Resume

    resume = Resume(
        full_name="Test",
        skills=["python", "aws", "kubernetes", "iam", "threat modeling"],
        titles=["security engineer"],
        seniority="senior",
        years_experience=8,
    )
    strong = Job(title="Senior Security Engineer", company="A",
                 description="python aws kubernetes iam threat modeling",
                 is_remote=True, salary_min=150000, salary_max=200000)
    weak = Job(title="Sales Manager", company="B",
               description="cold calling quota crm salesforce", is_remote=False)
    s_strong, _, _ = score_job(strong, resume, _default_match_cfg())
    s_weak, _, _ = score_job(weak, resume, _default_match_cfg())
    c.ok("strong job outscores weak job", s_strong > s_weak, f"{s_strong} vs {s_weak}")
    c.ok("scores are bounded 0-100", 0 <= s_strong <= 100 and 0 <= s_weak <= 100)


def _default_match_cfg() -> dict:
    from .config import DEFAULT_CONFIG
    return DEFAULT_CONFIG["match"]
