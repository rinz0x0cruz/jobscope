"""Dashboard JSON data contract (`dashboard --emit-json`).

Pins the shape the web build consumes and confirms the public redaction is applied
to the emitted JSON exactly as it is to the HTML dashboard. Fully offline.
"""
import json
import os
import tempfile

from jobscope.deliver import render
from jobscope.core.config import load_config
from jobscope.core.model import Application, Contact, Job, MailEvent
from jobscope.core.store import Store


def _seed(store):
    store.upsert_job(Job(
        source="indeed", title="Senior Security Engineer", company="Acme",
        url="https://jobs.example/acme-sse", is_remote=True, remote_scope="global",
        score=82.0, tier="Strong", resume_base="research",
        rationale="Strong overlap; ~1.7y experience (junior)").ensure_id())


def test_emit_json_shape():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)

        path = render.emit_json(cfg, store, public=False)
        assert os.path.basename(path) == "dashboard.json"
        data = json.load(open(path, encoding="utf-8"))
        assert {"generated", "total", "rows", "overview"} <= set(data)
        assert data["total"] == 1 and len(data["rows"]) == 1
        row = data["rows"][0]
        # core public-safe fields the web card needs
        for key in ("id", "title", "company", "location", "tier", "score",
                    "remote_scope", "url", "salary", "enrich", "brief"):
            assert key in row, key
        assert row["title"] == "Senior Security Engineer"
        # rationale persists via upsert; resume_base is assigned by `match`, not upsert
        assert row["rationale"]
        store.close()


def test_emit_json_public_is_redacted():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)

        path = render.emit_json(cfg, store, public=True)
        assert os.path.basename(path) == "dashboard.public.json"
        pub = json.load(open(path, encoding="utf-8"))
        row = pub["rows"][0]
        assert row["base"] == "" and row["rationale"] == "" and row["contacts"] == []
        # public-safe info is kept
        assert row["title"] == "Senior Security Engineer" and row["company"] == "Acme"
        store.close()


# --- P-A data contract: required keys -> accepted Python types ---------------
# Structural validator for build_data(), kept dependency-free on purpose
# (AGENTS.md: offline / dep-light, no jsonschema). Each spec maps a required key
# to the Python type(s) its value must have; `bool` is listed explicitly where a
# flag is expected so a stray int can't masquerade as one. Mirrors the TS types
# in web/src/lib/schema.ts and the artifact in jobscope/schema/dashboard.schema.json.

_TIERS = {"Strong", "Good", "Stretch", "Skip"}

_TOP_LEVEL = {
    "generated": str,
    "total": int,
    "rows": list,
    "overview": dict,
    "applications": list,
}

_JOB_ROW = {
    "id": str, "title": str, "company": str, "location": str,
    "remote": bool, "remote_scope": str, "url": str, "source": str,
    "score": (int, float), "tier": str, "base": str, "salary": str,
    "size": str, "funding": str, "country": str, "place": str,
    "industry": (str, type(None)), "rationale": str, "blocked": bool,
    "posted": (str, type(None)), "first_seen": str, "status": str,
    "last_seen": str, "closed_at": str, "enrich": dict, "brief": str,
    "contacts": list,
}

_OVERVIEW = {
    "funnel": dict, "gaps": list, "considered": int, "targets": list,
}

_APPLICATION = {
    "job_id": str, "company": str, "title": str, "status": str,
    "applied_at": str, "updated": str, "source": str, "timeline": list,
}

_TIMELINE_EVENT = {
    "date": str, "signal": str, "subject": str, "from": str,
}

# Optional sub-objects _enrich_summary() attaches; a present sub-object's keys
# must stay within these sets (mirrors EnrichSummary in schema.ts).
_STOCK_KEYS = {"ticker", "price", "change_pct", "market_cap", "public",
               "currency", "week52_low", "week52_high", "week52_pos_pct"}
_REDDIT_KEYS = {"sentiment", "summary", "count"}
_NEWS_KEYS = {"title", "link", "published", "source"}


def _require(obj, spec, where):
    """Assert obj is a dict with every key in spec present and correctly typed."""
    assert isinstance(obj, dict), f"{where} is {type(obj).__name__}, expected dict"
    for key, typ in spec.items():
        assert key in obj, f"{where}: missing key {key!r}"
        assert isinstance(obj[key], typ), (
            f"{where}.{key} is {type(obj[key]).__name__}, expected {typ}")


def _check_enrich(enrich, where):
    """Validate the (optional) sub-objects _enrich_summary() attaches."""
    assert isinstance(enrich, dict), f"{where} is not a dict"
    if "stock" in enrich:
        assert set(enrich["stock"]) <= _STOCK_KEYS, f"{where}.stock has unknown keys"
    if "reddit" in enrich:
        assert set(enrich["reddit"]) <= _REDDIT_KEYS, f"{where}.reddit has unknown keys"
    if "comp" in enrich:
        assert isinstance(enrich["comp"], dict), f"{where}.comp is not a dict"
    if "glassdoor" in enrich:
        assert isinstance(enrich["glassdoor"], dict), f"{where}.glassdoor is not a dict"
    if "news" in enrich:
        assert isinstance(enrich["news"], list), f"{where}.news is not a list"
        for i, item in enumerate(enrich["news"]):
            assert isinstance(item, dict), f"{where}.news[{i}] is not a dict"
            assert set(item) <= _NEWS_KEYS, f"{where}.news[{i}] has unknown keys"


def _validate_contract(data):
    """Structurally validate a build_data() payload against the P-A contract."""
    _require(data, _TOP_LEVEL, "payload")
    assert data["total"] == len(data["rows"]), "total != len(rows)"
    for i, row in enumerate(data["rows"]):
        _require(row, _JOB_ROW, f"rows[{i}]")
        assert row["tier"] in _TIERS, f"rows[{i}].tier={row['tier']!r} not a valid Tier"
        _check_enrich(row["enrich"], f"rows[{i}].enrich")
        for j, c in enumerate(row["contacts"]):
            assert isinstance(c, dict), f"rows[{i}].contacts[{j}] is not a dict"
    _require(data["overview"], _OVERVIEW, "overview")
    for i, pair in enumerate(data["overview"]["gaps"]):
        assert isinstance(pair, list) and len(pair) == 2, \
            f"overview.gaps[{i}] is not a [skill, count] pair"
        assert isinstance(pair[0], str) and isinstance(pair[1], (int, float)), \
            f"overview.gaps[{i}] has wrong element types"
    for i, app in enumerate(data["applications"]):
        _require(app, _APPLICATION, f"applications[{i}]")
        for j, ev in enumerate(app["timeline"]):
            _require(ev, _TIMELINE_EVENT, f"applications[{i}].timeline[{j}]")


def test_build_data_matches_contract():
    """P-A: the emitted payload structurally matches the Python<->TS data contract.

    Seeds a job + enrichment, an application, and a linked mail event so rows,
    overview, and applications (with a non-empty timeline) are all populated, then
    validates build_data() against the pure-Python key/type table above.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)
        jid = store.jobs()[0].id

        # enrichment -> populates rows[0].enrich (stock/comp/reddit/news branches)
        store.save_enrichment(
            "Acme",
            stock={"ticker": "ACME", "price": 12.5, "change_pct": -1.2, "public": True},
            comp={"levels_fyi": "L5", "min": 180000, "max": 240000, "currency": "USD"},
            reddit={"sentiment": "mixed", "summary": "ok place", "count": 7},
            news=[{"title": "Acme raises Series C", "link": "https://n/1",
                   "published": "2026-05-01", "source": "TechCrunch"}],
        )
        # an application + a linked inbound email -> applications[0].timeline
        store.set_application(Application(
            job_id=jid, status="applied", applied_at="2026-06-01",
            source="inbox", company="Acme", title="Senior Security Engineer"))
        store.upsert_mail_event(MailEvent(
            account="me@example.com", message_id="<m1@acme>", from_domain="acme.com",
            subject="Thanks for applying", date="2026-06-01T10:30:00",
            signal="confirmation", job_id=jid))

        data = render.build_data(cfg, store, public=False)

        # seam #5: applications is now part of the contract's top-level keys
        assert set(data) >= set(_TOP_LEVEL)
        _validate_contract(data)

        # the seed actually exercised each branch of the contract
        assert data["total"] == 1 and len(data["rows"]) == 1
        assert {"stock", "comp", "reddit", "news"} <= set(data["rows"][0]["enrich"])
        assert len(data["applications"]) == 1
        app = data["applications"][0]
        assert app["job_id"] == jid and app["status"] == "applied"
        assert app["source"] == "inbox" and app["applied_at"] == "2026-06-01"
        assert len(app["timeline"]) == 1
        assert app["timeline"][0] == {
            "date": "2026-06-01", "signal": "confirmation",
            "subject": "Thanks for applying", "from": "acme.com"}

        store.close()


def test_public_build_data_applications_empty():
    """The public payload emits `applications: []` (redaction), still contract-valid."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)
        store.set_application(Application(job_id=store.jobs()[0].id, status="applied"))

        data = render.build_data(cfg, store, public=True)
        _validate_contract(data)
        assert data["applications"] == []
        store.close()


def test_dashboard_schema_artifact_matches_contract():
    """The machine-readable JSON Schema artifact stays in sync with the contract.

    A dependency-free cross-check (no jsonschema): the artifact's declared
    required keys must match the pure-Python contract table this file enforces,
    so the .json artifact can't silently drift from the validated shape.
    """
    schema_path = os.path.join(
        os.path.dirname(render.__file__), "schema", "dashboard.schema.json")
    schema = json.load(open(schema_path, encoding="utf-8"))
    defs = schema["definitions"]
    assert set(schema["required"]) == set(_TOP_LEVEL)
    assert set(defs["JobRow"]["required"]) == set(_JOB_ROW)
    assert set(defs["Overview"]["required"]) == set(_OVERVIEW)
    assert set(defs["Application"]["required"]) == set(_APPLICATION)
    assert set(defs["ApplicationEvent"]["required"]) == set(_TIMELINE_EVENT)


def test_public_build_data_redacts_all_pii():
    """Regression lock: the public payload strips every private field -- referral
    contacts, score rationale, resume base, the application funnel, and search
    targets -- drops the whole applications list, and public rows expose no key
    beyond the documented safe set (so a new PII column can't silently ship).
    """
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        cfg["search"] = {"terms": ["ZZ_SECRET_TARGET"]}
        store = Store(cfg["output"]["db_path"])
        _seed(store)
        jid = store.jobs()[0].id
        store.save_contacts([Contact(
            id="c1", company="Acme", name="ZZ_SECRET_CONTACT", title="Recruiter",
            profile_url="https://example.test/zz")])
        store.set_application(Application(job_id=jid, status="applied"))

        full = render.build_data(cfg, store, public=False)
        pub = render.build_data(cfg, store, public=True)
        store.close()

    # sanity: the full build carries the PII the public build is meant to drop
    assert full["rows"][0]["contacts"], "seed should give the full build contacts"
    assert full["rows"][0]["rationale"], "seed should give the full build a rationale"
    assert full["overview"]["funnel"] and full["overview"]["targets"]
    assert full["applications"], "seed should give the full build an application"

    # public build strips all of it
    row = pub["rows"][0]
    assert row["contacts"] == []
    assert row["rationale"] == ""
    assert row["base"] == ""
    assert pub["overview"]["funnel"] == {}
    assert pub["overview"]["targets"] == []
    assert pub["applications"] == []
    # PII-contract: a public row carries no key beyond the known-safe contract set
    assert set(row) <= set(_JOB_ROW), f"unexpected public row keys: {set(row) - set(_JOB_ROW)}"


def test_public_json_has_no_pii_markers():
    """The emitted public dashboard JSON file must contain no private string --
    contact name, score rationale, search target, or email subject. A blunt
    substring guard so a redaction regression can't quietly leak PII to Pages.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        cfg["search"] = {"terms": ["ZZ_SECRET_TARGET"]}
        store = Store(cfg["output"]["db_path"])
        store.upsert_job(Job(
            source="indeed", title="Security Engineer", company="Acme",
            url="https://example.test/1",
            rationale="ZZ_SECRET_RATIONALE").ensure_id())
        jid = store.jobs()[0].id
        store.save_contacts([Contact(
            id="c1", company="Acme", name="ZZ_SECRET_CONTACT", title="Recruiter",
            profile_url="https://example.test/zz")])
        store.set_application(Application(
            job_id=jid, status="applied", company="Acme", title="Security Engineer"))
        store.upsert_mail_event(MailEvent(
            account="me@example.com", message_id="<m1@acme>", from_domain="acme.com",
            subject="ZZ_SECRET_SUBJECT", date="2026-06-01T10:00:00",
            signal="confirmation", job_id=jid))

        path = render.emit_json(cfg, store, public=True)
        store.close()
        text = open(path, encoding="utf-8").read()

    for marker in ("ZZ_SECRET_CONTACT", "ZZ_SECRET_RATIONALE",
                   "ZZ_SECRET_TARGET", "ZZ_SECRET_SUBJECT"):
        assert marker not in text, f"PII leaked into the public dashboard JSON: {marker}"
