"""Dashboard JSON emitter.

Assembles the dashboard data contract (per-job records, overview, and the
Applications board) from the stored jobs and enrichment, and writes it to
``data/dashboard[.public].json`` for the React web app (``web/``) to consume.
"""
from __future__ import annotations

import html
import json
import os
import re
from typing import Any

from jobscope.core import companies
from jobscope.core.store import now_iso

TIER_COLORS = {"Strong": "#16a34a", "Good": "#2563eb", "Stretch": "#d97706", "Skip": "#6b7280"}


def _profile_data(cfg: dict, store) -> dict | None:
    """The résumé-derived search profile for the dashboard (shown behind the site
    unlock, stripped from the public build): the editable ``profile.yaml`` when it
    exists, else built on the fly from the stored résumé. ``None`` with no résumé.
    """
    from jobscope.analyze import profile as _profile
    prof = _profile.load(cfg)
    if prof:
        return prof
    resumes = store.list_resumes()
    if resumes:
        name, resume = resumes[0]
        return _profile.build_profile(resume, cfg, name)
    return None


def _applied_outreach_data(store) -> list:
    """Pre-computed HR contacts for the companies you're actively applied to, joined
    with each application's status/date (shown behind the site unlock, stripped from
    the public build). Only companies that are still active AND have stored contacts
    appear, ordered most-recently-active first (mirrors ``outreach-scan``)."""
    contacts_by = {c["company"]: c for c in store.list_company_contacts()}
    out = []
    for r in store.active_application_companies(limit=1000):
        cc = contacts_by.get(r["company"])
        if not cc or not cc.get("contacts"):
            continue
        out.append({
            "company": r["company"],
            "domain": cc.get("domain") or "",
            "status": r.get("status") or "",
            "applied_at": (r.get("applied_at") or "")[:10],
            "contacts": cc["contacts"],
        })
    return out


def build_data(cfg: dict, store, public: bool = False) -> dict:
    """Assemble the dashboard payload (rows + overview) as a plain dict.

    This is the data contract the web dashboard build consumes; it reuses the exact
    per-job and overview shapes the HTML renderer uses, and applies the public
    redaction when ``public`` is set.
    """
    jobs = store.jobs(order_by_score=True)
    # Skip-tier roles (off-target / too-senior / filtered) are hidden from the
    # dashboard by default, so the pages show only actionable matches. Set
    # output.include_skip: true to publish them anyway.
    if not (cfg.get("output", {}) or {}).get("include_skip"):
        jobs = [j for j in jobs if (j.tier or "Skip") != "Skip"]
    rows = [_job_record(j, store.get_enrichment(j.company) if j.company else {}, store)
            for j in jobs]
    overview = _overview_data(cfg, store)
    apps = [] if public else _application_records(store)
    profile = None if public else _profile_data(cfg, store)
    applied_outreach = [] if public else _applied_outreach_data(store)
    if public:
        _redact_public(rows, overview)
    return {"generated": now_iso(), "total": len(rows), "rows": rows,
            "overview": overview, "applications": apps, "profile": profile,
            "applied_outreach": applied_outreach}


def _json_path(cfg: dict, public: bool) -> str:
    db = cfg["output"].get("db_path") or "data/jobscope.db"
    directory = os.path.dirname(os.path.abspath(db)) or "."
    return os.path.join(directory, "dashboard.public.json" if public else "dashboard.json")


def emit_json(cfg: dict, store, public: bool = False) -> str:
    """Write the dashboard payload to data/dashboard[.public].json; return the path."""
    data = build_data(cfg, store, public=public)
    path = _json_path(cfg, public)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    return path


def emit_web(cfg: dict, store) -> str | None:
    """Mirror the un-redacted payload into the web app's data path so a plain
    ``npm run dev`` / ``npm run build`` bakes fresh data (issue #5).

    The web SPA imports ``web/src/data/dashboard.json``; ``emit_json`` only writes
    ``data/dashboard.json``, so without this the dev build shows stale data. Always
    writes the *un-redacted* payload -- it is the local dev copy and is gitignored.
    The publish scripts never call this (they manage ``web/src/data`` deliberately,
    copying the redacted public payload), so it can't leak private data into a
    published build. Returns the path written, or ``None`` when the web source tree
    isn't present (e.g. jobscope installed without the repo checkout).
    """
    web_dir = os.path.join("web", "src", "data")
    if not os.path.isdir(web_dir):
        return None
    path = os.path.join(web_dir, "dashboard.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build_data(cfg, store, public=False), fh, ensure_ascii=False,
                  separators=(",", ":"))
    return path


def _redact_public(rows: list[dict], overview: dict) -> None:
    """Strip private fields in place for a publicly-hosted (GitHub Pages) dashboard.

    Removes third-party referral contacts, score rationale, resume-variant
    labels, and the archived job-description snapshot from every job, plus the
    application funnel and search terms from the overview -- leaving only public
    job info and fit scores. The ``blocked`` flag is already computed in
    ``_job_record``, so clearing ``rationale`` here is safe.
    """
    for r in rows:
        r["contacts"] = []
        r["rationale"] = ""
        r["base"] = ""
        r["description"] = ""
    overview["funnel"] = {}
    overview["targets"] = []


def _overview_data(cfg: dict, store) -> dict:
    """Extra summary data for the Overview tab: application funnel, skill gaps, targets."""
    funnel: dict[str, int] = {}
    try:
        for a in store.applications():
            s = a.get("status") or "new"
            funnel[s] = funnel.get(s, 0) + 1
    except Exception:  # noqa: BLE001 - overview is best-effort, never break the dashboard
        pass
    gaps: list = []
    considered = 0
    try:
        from jobscope.analyze.insights import skill_gap
        considered, ranked = skill_gap(store, top=8)
        gaps = [[s, c] for s, c, _ex in ranked]
    except Exception:  # noqa: BLE001
        pass
    targets = list((cfg.get("search") or {}).get("terms") or [])
    return {"funnel": funnel, "gaps": gaps, "considered": considered, "targets": targets}


def _summarize(text: str, limit: int = 220) -> str:
    """One-line preview of an email body: collapse whitespace and truncate on a
    word boundary. Deterministic (no AI); the raw snippet is only present when
    ``inbox.store_snippets`` is enabled, so this is "" otherwise."""
    s = re.sub(r"\s+", " ", text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "..."


def _application_records(store) -> list[dict[str, Any]]:
    """Per-application records (company/title/status + email timeline) for the
    dashboard's Applications board. Best-effort: never breaks the dashboard."""
    try:
        apps = store.applications()
    except Exception:  # noqa: BLE001
        return []
    events: dict[str, list] = {}
    try:
        for e in store.mail_events():
            events.setdefault(e.get("job_id") or "", []).append(e)
    except Exception:  # noqa: BLE001
        events = {}
    out: list[dict[str, Any]] = []
    for a in apps:
        jid = a.get("job_id") or ""
        evs = sorted(events.get(jid, []),
                     key=lambda e: (e.get("date") or "", e.get("first_seen") or ""))
        out.append({
            "job_id": jid,
            "company": a.get("company") or "",
            "title": a.get("title") or "",
            "status": a.get("status") or "new",
            "applied_at": a.get("applied_at") or "",
            "updated": a.get("updated") or "",
            "source": a.get("source") or "",
            "timeline": [{
                "date": (e.get("date") or "")[:10],
                "signal": e.get("signal") or "",
                "subject": e.get("subject") or "",
                "from": e.get("from_domain") or "",
                "summary": _summarize(e.get("snippet") or ""),
            } for e in evs],
        })
    return out


_COUNTRY_CODES = {
    "in": "India", "us": "United States", "usa": "United States", "uk": "United Kingdom",
    "gb": "United Kingdom", "uae": "United Arab Emirates", "ae": "United Arab Emirates",
    "sg": "Singapore", "de": "Germany", "fr": "France", "il": "Israel", "my": "Malaysia",
    "it": "Italy", "ca": "Canada", "au": "Australia", "nl": "Netherlands", "es": "Spain",
    "ie": "Ireland", "ch": "Switzerland", "se": "Sweden", "pl": "Poland", "jp": "Japan",
    "br": "Brazil", "mx": "Mexico", "ph": "Philippines", "id": "Indonesia", "pt": "Portugal",
    "can": "Canada", "gbr": "United Kingdom", "u.s": "United States", "u.s.": "United States",
    "u.k": "United Kingdom",
}


def _country_of(job) -> str:
    """Best-effort country from a messy location string.

    Strips parenthetical / work-mode noise ("United States (Remote)", "US - Remote",
    "CAN-Remote" -> United States / Canada) and maps common codes, so the country
    facet stays tidy instead of fragmenting into one option per posting variant.
    """
    loc = (job.location or "").strip()
    if not loc:
        return "Remote" if job.is_remote else ""
    cleaned = re.sub(r"\([^)]*\)", " ", loc)                       # drop "(Remote)" etc.
    _wm = ("remote", "onsite", "on-site", "hybrid", "anywhere", "flexible", "wfh")
    for seg in reversed([s for s in re.split(r"[,;/]", cleaned) if s.strip()]):
        words = [w for w in seg.split() if w.strip(".-") and w.lower().strip(".-") not in _wm]
        cand = re.sub(r"-?(?:remote|wfh)$", "", " ".join(words), flags=re.I).strip(" .-")
        if cand:
            return _COUNTRY_CODES.get(cand.lower(), cand)
    return "Remote" if job.is_remote else ""


_IN_STATES = {
    "mh": "Maharashtra", "ka": "Karnataka", "ts": "Telangana", "tn": "Tamil Nadu",
    "dl": "Delhi", "hr": "Haryana", "up": "Uttar Pradesh", "gj": "Gujarat",
    "wb": "West Bengal", "rj": "Rajasthan", "pb": "Punjab", "kl": "Kerala",
    "ap": "Andhra Pradesh", "mp": "Madhya Pradesh", "ch": "Chandigarh", "ga": "Goa",
}


def _place_of(job) -> str:
    """City / region for the location facet ('Pune, â€¦' -> Pune; 'MH, IN' -> Maharashtra)."""
    loc = (job.location or "").strip()
    if not loc:
        return "Remote" if job.is_remote else ""
    segs = [s.strip() for s in loc.split(",") if s.strip()]
    if not segs:
        return ""
    first = segs[0]
    low = first.lower()
    if low in ("remote", "anywhere"):
        return "Remote"
    last = segs[-1].lower().strip(". ")
    if last in ("in", "india") and low in _IN_STATES:   # Indeed India state codes
        return _IN_STATES[low]
    return first


def _jd_snapshot(text: str, limit: int = 6000) -> str:
    """Trimmed, HTML-cleaned job-description snapshot for the drawer archive (issue #30).

    The full JD is stored in ``jobs.description`` (sometimes with ATS HTML markup);
    we convert it to readable text and surface a length-bounded copy so a role stays
    viewable after the original listing is taken down. Stripped for the public build.
    """
    s = text or ""
    # HTML -> text: keep block breaks as newlines, bullet <li>, drop other tags, unescape.
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\u2022 ", s)
    s = re.sub(r"(?i)</(p|div|li|ul|ol|h[1-6]|tr|section)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    if len(s) <= limit:
        return s
    cut = s.rfind(" ", 0, limit)
    return s[: cut if cut > limit - 200 else limit].rstrip() + "\u2026"


def _job_record(job, enr: dict, store) -> dict[str, Any]:
    salary = _fmt_salary(job)
    contacts = store.contacts_for(job.company) if job.company else []
    rationale = job.rationale or ""
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": ("Remote" if job.is_remote else job.location) or job.location,
        "remote": bool(job.is_remote),
        "remote_scope": job.remote_scope or "",
        "url": job.url,
        "source": job.source,
        "score": job.score,
        "tier": job.tier or "Skip",
        "base": job.resume_base or "",
        "salary": salary,
        "size": companies.company_size(job.company)[1] if job.company else "",
        "funding": companies.company_funding(job.company) if job.company else "",
        "country": _country_of(job),
        "place": _place_of(job),
        "industry": job.company_industry,
        "rationale": rationale,
        "blocked": "â›”" in rationale,
        "posted": job.date_posted,
        "first_seen": job.first_seen or "",
        "status": job.status or "open",
        "last_seen": job.last_seen or "",
        "closed_at": job.closed_at or "",
        "enrich": _enrich_summary(enr),
        "brief": ((enr or {}).get("brief") or {}).get("text", "") if enr else "",
        "description": _jd_snapshot(job.description),
        "contacts": [{"name": c.get("name"), "title": c.get("title"),
                      "url": c.get("profile_url") or c.get("search_url")} for c in contacts],
    }


def _enrich_summary(enr: dict) -> dict[str, Any]:
    if not enr:
        return {}
    out: dict[str, Any] = {}
    stock = enr.get("stock") or {}
    if stock:
        out["stock"] = {k: stock.get(k) for k in ("ticker", "price", "change_pct",
                                                  "market_cap", "public", "currency",
                                                  "week52_low", "week52_high", "week52_pos_pct")
                        if k in stock}
    comp = enr.get("comp") or {}
    if comp:
        out["comp"] = comp
    reddit = enr.get("reddit") or {}
    if reddit:
        out["reddit"] = {"sentiment": reddit.get("sentiment"),
                         "summary": reddit.get("summary"),
                         "count": reddit.get("count")}
    news = enr.get("news") or []
    if news:
        out["news"] = news[:3]
    gd = enr.get("glassdoor") or {}
    if gd:
        out["glassdoor"] = gd
    return out


def _fmt_salary(job) -> str:
    lo, hi = job.salary_min, job.salary_max
    if not lo and not hi:
        return ""
    cur = {"USD": "$", "EUR": "â‚¬", "GBP": "Â£", "INR": "â‚¹"}.get((job.currency or "").upper(), "")
    unit = f"/{job.salary_interval}" if job.salary_interval else ""

    def f(v):
        return f"{cur}{int(v):,}" if v else ""

    if lo and hi:
        return f"{f(lo)}â€“{f(hi)}{unit}"
    return f"{f(lo or hi)}{unit}"
