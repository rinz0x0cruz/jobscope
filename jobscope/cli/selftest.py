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
    from ..core.model import Job, job_id, slugify

    id1 = job_id("indeed", "Security Engineer", "Acme", "https://x/y")
    id2 = job_id("indeed", "Security Engineer", "Acme", "https://x/y")
    id3 = job_id("indeed", "Security Engineer", "Acme", "https://x/z")
    c.ok("job_id is deterministic", id1 == id2)
    c.ok("job_id varies by url", id1 != id3)
    c.ok("slugify is filesystem-safe", slugify("Foo Bar!/Baz") == "foo-bar-baz")
    j = Job(source="indeed", title="SE", company="Acme").ensure_id()
    c.ok("job.ensure_id fills id", bool(j.id))

    # --- config -----------------------------------------------------------
    from ..core.config import DEFAULT_CONFIG, _deep_merge, load_config

    merged = _deep_merge(DEFAULT_CONFIG, {"search": {"location": "Berlin"}})
    c.ok("deep_merge overrides leaf", merged["search"]["location"] == "Berlin")
    c.ok("deep_merge keeps siblings", merged["search"]["results_wanted"] == 25)
    c.ok("default weights sum ~1.0",
         abs(sum(DEFAULT_CONFIG["match"]["weights"].values()) - 1.0) < 1e-9)
    cfg = load_config(None)
    c.ok("load_config returns defaults",
         isinstance(cfg.get("ai"), dict) and DEFAULT_CONFIG["ai"]["provider"] == "groq")
    from ..core import ai as _ai
    c.ok("quorum strategy_generative default", _ai.strategy_for(DEFAULT_CONFIG, "generative") == "council")
    c.ok("quorum strategy_classify default", _ai.strategy_for(DEFAULT_CONFIG, "classify") == "ensemble")
    c.ok("quorum strategy_for empty -> None", _ai.strategy_for({"quorum": {}}, "generative") is None)
    from ..core.model import Job as _J, Resume as _R
    from ..analyze.match import ai_review as _air
    _tiers = {"strong": 75, "good": 55, "stretch": 35}
    c.ok("ai_review near_boundary",
         _air.near_boundary(73, _tiers, 8) and not _air.near_boundary(90, _tiers, 8))
    c.ok("ai_review tier_of", _air._tier_of(80, _tiers) == "Strong" and _air._tier_of(10, _tiers) == "Skip")
    c.ok("ai_review off -> None",
         _air.review_job(cfg, None, _J(source="x", title="t", company="c"), _R(), 73.0, "Good", _tiers) is None)

    # --- store ------------------------------------------------------------
    from ..core.model import Application, Resume
    from ..core.store import Store

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

        store.save_resume(Resume(full_name="Con", skills=["audit"]), name="consulting")
        c.ok("named resumes list", {n for n, _ in store.list_resumes()} == {"default", "consulting"})
        c.ok("meta round-trips", (store.meta_set("m", "v"), store.meta_get("m")) [1] == "v")
        store.update_score(j.id, 90, "Strong", "x", resume_base="consulting")
        c.ok("resume_base persists", store.get_job(j.id).resume_base == "consulting")
        store.close()

    # --- match (deterministic scoring + filters) -------------------------
    try:
        from ..analyze import match  # noqa: F401
        _selftest_match(c)
        _selftest_filters(c)
    except ImportError:
        pass  # not yet built

    # --- inbox (deterministic email classification; no network) ----------
    _selftest_inbox(c)

    # --- ats (direct company boards; HTTP stubbed, no network) -----------
    from ..ingest import ats

    def _stub(url, **_kw):
        if "greenhouse" in url:
            return {"jobs": [
                {"title": "Security Engineer", "location": {"name": "Bengaluru, India"},
                 "absolute_url": "https://x/1", "content": "<p>a &amp; b</p>",
                 "updated_at": "2026-06-30T00:00:00-04:00"},
                {"title": "Account Executive", "location": {"name": "Bengaluru, India"},
                 "absolute_url": "https://x/2", "content": "sell", "updated_at": ""},
            ]}
        return None

    _orig_get_json = ats.httpx.get_json
    ats.httpx.get_json = _stub
    try:
        c.ok("ats resolves known slug",
             ats._resolve("databricks") == ("databricks", "greenhouse", "databricks"))
        c.ok("ats resolves explicit override", ats._resolve("A|lever|a") == ("A", "lever", "a"))
        boards = ats.fetch_company("Databricks", "greenhouse", "databricks")
        c.ok("ats parses greenhouse board", len(boards) == 2 and boards[0].source == "ats")
        c.ok("ats strips + unescapes html", boards[0].description == "a & b")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "a.db"))
            cfg2 = load_config(None)
            cfg2["search"].update(terms=["security engineer"], country_indeed="India",
                                  is_remote=True, companies=["databricks"])
            c.ok("ats run filters role + upserts", ats.run(cfg2, store) == 1)
            jid = store.jobs()[0].id
            c.ok("reconcile ignores empty liveset",
                 store.reconcile_open("ats", "databricks", set()) == 0)
            c.ok("reconcile closes missing job",
                 store.reconcile_open("ats", "databricks", {"https://other"}) == 1)
            c.ok("closed status persists", store.get_job(jid).status == "closed")
            store.close()
    finally:
        ats.httpx.get_json = _orig_get_json

    total = c.passed + c.failed
    print(f"\n  {c.passed}/{total} checks passed")
    return 0 if c.failed == 0 else 1


def _selftest_inbox(c: "_Check") -> None:
    from ..ingest import mailrules
    from ..core.model import Application, MailEvent
    from ..core.store import Store

    c.ok("mail: confirmation classified",
         mailrules.classify_signal("no-reply@greenhouse.io",
                                   "Thank you for applying to Databricks", "") == "confirmation")
    c.ok("mail: rejection beats interview",
         mailrules.classify_signal(
             "x@lever.co", "Update",
             "We enjoyed your interview but unfortunately will not be moving forward.")
         == "rejection")
    c.ok("mail: status advance is monotonic",
         mailrules.advance_status("offer", "applied") == "offer")
    c.ok("mail: rejection is terminal",
         mailrules.advance_status("rejected", "interview") == "rejected")
    company, role = mailrules.parse_company_role(
        "Databricks Recruiting", "greenhouse.io",
        "Your application for the Security Engineer role at Databricks", "")
    c.ok("mail: parses company + role", company == "Databricks" and "Security Engineer" in role)

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "m.db"))
        ev = MailEvent(account="me@x", message_id="<a@x>", signal="confirmation",
                       job_id="mail:1", company="Acme")
        c.ok("mail: event upserts", store.upsert_mail_event(ev) is True)
        c.ok("mail: event dedupes", store.upsert_mail_event(ev) is False)
        store.set_application(Application(job_id="mail:1", status="applied",
                                         company="Acme", title="Engineer", source="inbox"))
        c.ok("mail: email-only app shows company",
             store.applications()[0]["company"] == "Acme")
        store.close()


def _selftest_match(c: "_Check") -> None:
    from ..analyze.match import score_job
    from ..core.model import Job, Resume

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


def _selftest_filters(c: "_Check") -> None:
    from ..analyze.match import apply_filters, clearance_flags, no_sponsorship, select_base
    from ..core.model import Job, Resume

    clr = Job(title="Engineer", company="A", description="Active security clearance required")
    c.ok("clearance detected", bool(clearance_flags(clr)))
    c.ok("no-sponsorship detected", no_sponsorship(Job(description="we cannot sponsor visas")))
    c.ok("filter blocks clearance",
         apply_filters(clr, {"exclude_clearance": True}) is not None)
    c.ok("filter blocks company",
         apply_filters(Job(company="Acme"), {"block_companies": ["acme"]}) is not None)
    c.ok("filter passes clean job", apply_filters(Job(company="Z", description="ok"), {}) is None)
    from ..analyze.match import required_experience_years
    c.ok("exp: senior title implies ~4y",
         required_experience_years(Job(title="Senior Software Engineer")) == 4.0)
    c.ok("exp: explicit N+ years parsed",
         required_experience_years(Job(title="Engineer", description="5+ years of experience")) == 5.0)
    c.ok("exp: no signal -> None",
         required_experience_years(Job(title="Software Engineer", description="great team")) is None)
    c.ok("exp filter blocks over cap",
         apply_filters(Job(title="Staff Engineer"), {"max_years_experience": 2}) is not None)
    c.ok("exp filter keeps at/below cap",
         apply_filters(Job(title="Engineer", description="2+ years"), {"max_years_experience": 2}) is None)
    from ..ingest import scrape
    c.ok("remote: concrete city overrides stray flag",
         scrape._derive_remote(True, "Dublin, County Dublin, Ireland", "Security Engineer") is False)
    c.ok("remote: explicit keyword is remote",
         scrape._derive_remote(False, "Remote - India", "Security Engineer") is True)
    r1 = Resume(skills=["yara", "malware analysis"], seniority="mid")
    r2 = Resume(skills=["audit", "compliance"], seniority="mid")
    job = Job(title="Malware Analyst", description="yara malware analysis " * 5)
    _, _, _, base = select_base(job, [("research", r1), ("consulting", r2)], _default_match_cfg())
    c.ok("select_base picks best resume", base == "research", base)
    from ..core.companies import company_quality, company_size, company_funding
    c.ok("company_quality: elite", company_quality("Google")[0] == 1.0)
    c.ok("company_quality: unknown neutral", company_quality("Obscure Widgets LLC")[0] == 0.5)
    c.ok("company_size: mega", company_size("Amazon Web Services") == (1.00, "mega"))
    c.ok("company_size: startup band", company_size("Wiz")[1] == "small")
    c.ok("company_size: unknown neutral", company_size("Obscure Widgets LLC") == (0.5, ""))
    c.ok("company_funding: public", company_funding("CrowdStrike") == "public")
    c.ok("company_funding: unicorn", company_funding("Wiz") == "unicorn")
    c.ok("company_funding: unknown blank", company_funding("Obscure Widgets LLC") == "")
    from ..analyze.match import _company_score
    big = {"prefer_company_size": "large"}
    small = {"prefer_company_size": "small"}
    c.ok("prefer large ranks mega high", _company_score(Job(company="Amazon"), big)[0] > 0.9)
    c.ok("prefer small demotes mega",
         _company_score(Job(company="Amazon"), small)[0] < _company_score(Job(company="Amazon"), big)[0])
    from ..analyze.match import _job_lean
    c.ok("discipline: technical job leans +",
         _job_lean(Job(title="Malware Reverse Engineer", description="ghidra exploit disassembly")) > 0.3)
    c.ok("discipline: advisory job leans -",
         _job_lean(Job(title="GRC Consultant", description="compliance audit risk assessment")) < -0.3)
    tech_r = Resume(skills=["python"], titles=["Security Analyst"],
                    raw_text="reverse engineering malware ghidra exploit")
    adv_r = Resume(skills=["python"], titles=["Security Analyst"],
                   raw_text="grc compliance audit advisory governance")
    tie = [("consulting", adv_r), ("research", tech_r)]        # advisory listed first
    tech_job = Job(title="Malware RE", description="reverse engineering exploit ghidra " * 4)
    c.ok("discipline routes technical -> research",
         select_base(tech_job, tie, _default_match_cfg())[3] == "research")


def _default_match_cfg() -> dict:
    from ..core.config import DEFAULT_CONFIG
    return DEFAULT_CONFIG["match"]
