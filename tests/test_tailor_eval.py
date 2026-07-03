"""Golden-set eval for AI resume tailoring (``tailor._tailored_summary``).

Key-free: the model is mocked, so this runs in CI with no network and no keys. It is a
regression gate on **prompt construction**, the **untrusted-JD guardrail** (OWASP LLM01),
and **PII minimization** (contact details are never sent to the model) — not a judgement of
model quality. Fixtures: tests/fixtures/tailor_eval.jsonl.

Invariants asserted for every golden case:
  1. the tailored summary uses the model's text;
  2. the system prompt carries the "never invent" guardrail;
  3. the untrusted job description is passed as data (in the user message) and never
     promoted into the system prompt — so an injected "ignore instructions" stays inert;
  4. contact PII (email, phone) is never included in either prompt.
Plus: with AI unavailable, the summary is deterministic and fabricates nothing.
"""
import json
from pathlib import Path

from jobscope import ai, tailor
from jobscope.config import load_config
from jobscope.model import Job, Resume

FIXTURES = Path(__file__).parent / "fixtures" / "tailor_eval.jsonl"

_EMAIL = "jane.doe@personal-example.com"
_PHONE = "+1-555-867-5309"


def _resume():
    return Resume(
        full_name="Jane Doe", email=_EMAIL, phone=_PHONE, location="Remote",
        summary="Security engineer.",
        skills=["python", "aws", "kubernetes", "iam", "threat modeling"],
        titles=["Security Engineer"], seniority="senior", years_experience=8,
        raw_text="# Jane Doe\n\n## Summary\nSecurity engineer.\n",
    )


def _job(case):
    return Job(source="test", title=case["title"], company=case["company"],
               url="https://x/1", description=case["description"]).ensure_id()


def _cases():
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield json.loads(line)


def test_tailored_summary_golden(monkeypatch):
    cfg = load_config(None)
    resume = _resume()
    cases = list(_cases())
    assert cases, "golden set is empty"

    for case in cases:
        cap = {}

        def fake_chat(cfg, store, system=None, user=None, _cap=cap, _c=case, **kw):
            _cap["system"], _cap["user"] = system, user
            return _c["mock_reply"]

        monkeypatch.setattr(ai, "chat", fake_chat)
        job = _job(case)
        analysis = tailor.analyze(resume, job)
        out = tailor._tailored_summary(cfg, None, resume, job, analysis)

        # 1. uses the model's text
        assert out == case["mock_reply"].strip(), case["id"]
        # 2. guardrail in the system prompt
        assert "never invent" in cap["system"].lower(), case["id"]
        # 3. untrusted JD is data (user), never promoted into the system prompt
        assert case["description"][:60] in cap["user"], case["id"]
        assert case["description"] not in cap["system"], case["id"]
        # 4. PII minimization: contact details never reach the model
        for pii in (_EMAIL, _PHONE):
            assert pii not in cap["user"], case["id"]
            assert pii not in cap["system"], case["id"]


def test_tailored_summary_fallback_no_fabrication(monkeypatch):
    """AI unavailable -> deterministic summary grounded in real resume facts."""
    monkeypatch.setattr(ai, "chat", lambda *a, **k: None)
    cfg = load_config(None)
    resume = _resume()
    job = _job({"title": "Cloud Engineer", "company": "Acme",
                "description": "aws terraform kubernetes"})
    analysis = tailor.analyze(resume, job)
    out = tailor._tailored_summary(cfg, None, resume, job, analysis)
    assert out, "fallback summary should be non-empty"
    assert "8" in out or "senior" in out.lower()
