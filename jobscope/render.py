"""Static HTML dashboard renderer.

Builds a single self-contained ``dashboard.html`` (inline CSS/JS, no external
deps) from the stored jobs and any enrichment. Mirrors the threatscope/exploitrank
dashboard approach: ranked rows, tier chips, click-to-filter, and a search box.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any

from . import companies
from .store import now_iso

TIER_COLORS = {"Strong": "#16a34a", "Good": "#2563eb", "Stretch": "#d97706", "Skip": "#6b7280"}


def build(cfg: dict, store, public: bool = False) -> str:
    jobs = store.jobs(order_by_score=True)
    rows = []
    for j in jobs:
        enr = store.get_enrichment(j.company) if j.company else {}
        rows.append(_job_record(j, enr, store))
    overview = _overview_data(cfg, store)
    if public:
        _redact_public(rows, overview)
        path = cfg["output"].get("public_dashboard_path") or cfg["output"]["dashboard_path"]
    else:
        path = cfg["output"]["dashboard_path"]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    htmltext = _render(rows, overview)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(htmltext)
    return path


def _redact_public(rows: list[dict], overview: dict) -> None:
    """Strip private fields in place for a publicly-hosted (GitHub Pages) dashboard.

    Removes third-party referral contacts, score rationale, and resume-variant
    labels from every job, plus the application funnel and search terms from the
    overview -- leaving only public job info and fit scores. The ``blocked`` flag
    is already computed in ``_job_record``, so clearing ``rationale`` here is safe.
    """
    for r in rows:
        r["contacts"] = []
        r["rationale"] = ""
        r["base"] = ""
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
        from .insights import skill_gap
        considered, ranked = skill_gap(store, top=8)
        gaps = [[s, c] for s, c, _ex in ranked]
    except Exception:  # noqa: BLE001
        pass
    targets = list((cfg.get("search") or {}).get("terms") or [])
    return {"funnel": funnel, "gaps": gaps, "considered": considered, "targets": targets}


_COUNTRY_CODES = {
    "in": "India", "us": "United States", "usa": "United States", "uk": "United Kingdom",
    "gb": "United Kingdom", "uae": "United Arab Emirates", "ae": "United Arab Emirates",
    "sg": "Singapore", "de": "Germany", "fr": "France", "il": "Israel", "my": "Malaysia",
    "it": "Italy", "ca": "Canada", "au": "Australia", "nl": "Netherlands", "es": "Spain",
    "ie": "Ireland", "ch": "Switzerland", "se": "Sweden", "pl": "Poland", "jp": "Japan",
    "br": "Brazil", "mx": "Mexico", "ph": "Philippines", "id": "Indonesia", "pt": "Portugal",
}


def _country_of(job) -> str:
    """Best-effort country from a JobSpy location string ('Remote, IN' / 'MH, IN' -> India)."""
    loc = (job.location or "").strip()
    if not loc:
        return "Remote" if job.is_remote else ""
    segs = [s.strip() for s in loc.split(",") if s.strip()]
    if not segs:
        return ""
    last = segs[-1].strip(". ")
    return _COUNTRY_CODES.get(last.lower(), last)


_IN_STATES = {
    "mh": "Maharashtra", "ka": "Karnataka", "ts": "Telangana", "tn": "Tamil Nadu",
    "dl": "Delhi", "hr": "Haryana", "up": "Uttar Pradesh", "gj": "Gujarat",
    "wb": "West Bengal", "rj": "Rajasthan", "pb": "Punjab", "kl": "Kerala",
    "ap": "Andhra Pradesh", "mp": "Madhya Pradesh", "ch": "Chandigarh", "ga": "Goa",
}


def _place_of(job) -> str:
    """City / region for the location facet ('Pune, …' -> Pune; 'MH, IN' -> Maharashtra)."""
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
        "blocked": "⛔" in rationale,
        "posted": job.date_posted,
        "first_seen": job.first_seen or "",
        "status": job.status or "open",
        "last_seen": job.last_seen or "",
        "closed_at": job.closed_at or "",
        "enrich": _enrich_summary(enr),
        "brief": ((enr or {}).get("brief") or {}).get("text", "") if enr else "",
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
                                                  "market_cap", "public") if k in stock}
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
    cur = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get((job.currency or "").upper(), "")
    unit = f"/{job.salary_interval}" if job.salary_interval else ""

    def f(v):
        return f"{cur}{int(v):,}" if v else ""

    if lo and hi:
        return f"{f(lo)}–{f(hi)}{unit}"
    return f"{f(lo or hi)}{unit}"


def _render(rows: list[dict], overview: dict | None = None) -> str:
    data = json.dumps(rows).replace("</", "<\\/")
    ov = json.dumps(overview or {}).replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__DATA__", data)
            .replace("__OVERVIEW__", ov)
            .replace("__GENERATED__", html.escape(now_iso()))
            .replace("__TOTAL__", str(len(rows))))


_TEMPLATE = r"""<!doctype html>
<html lang="en" class="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>jobscope</title>
<style>
:root{
  --bg:#0a0a0b; --bg2:#0e0e10; --card:#121214; --card-h:#17171b;
  --border:#1f1f23; --border-h:#2c2c33; --fg:#ededef; --dim:#a1a1aa; --mute:#6a6a73;
  --accent:#7c6cff; --accent-dim:rgba(124,108,255,.14);
  --strong:#22c55e; --good:#3b82f6; --stretch:#f59e0b; --skip:#71717a;
  --radius:14px; --shadow:0 10px 30px -12px rgba(0,0,0,.6);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  --mono:"SF Mono",ui-monospace,"Cascadia Code","Segoe UI Mono",Menlo,Consolas,monospace;
}
html.light{
  --bg:#fafafa; --bg2:#f4f4f5; --card:#ffffff; --card-h:#fbfbfd;
  --border:#e7e7ea; --border-h:#d9d9de; --fg:#18181b; --dim:#52525b; --mute:#8a8a93;
  --accent:#6d5cf0; --accent-dim:rgba(109,92,240,.10); --shadow:0 8px 24px -14px rgba(0,0,0,.25);
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:var(--bg); color:var(--fg); font-family:var(--font);
  font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased;
  background-image:radial-gradient(900px 500px at 88% -8%, var(--accent-dim), transparent 60%);
  background-attachment:fixed;
}
a{color:inherit}
.tnum{font-variant-numeric:tabular-nums}
/* header */
header{position:sticky; top:0; z-index:20; padding:14px 24px;
  display:flex; gap:18px; align-items:center; flex-wrap:wrap;
  background:color-mix(in srgb, var(--bg) 72%, transparent);
  backdrop-filter:saturate(160%) blur(14px); -webkit-backdrop-filter:saturate(160%) blur(14px);
  border-bottom:1px solid var(--border);}
.brand{display:flex; align-items:center; gap:10px}
.logo{width:22px;height:22px;border-radius:7px;background:linear-gradient(140deg,var(--accent),#b7a6ff);
  box-shadow:0 0 0 1px rgba(255,255,255,.06), 0 6px 16px -6px var(--accent)}
h1{font-size:16px; margin:0; letter-spacing:-.2px; font-weight:650}
.sub{color:var(--mute); font-size:12px; margin-top:1px}
.grow{flex:1}
.search{position:relative}
.search svg{position:absolute; left:11px; top:50%; transform:translateY(-50%); opacity:.5}
#q{background:var(--card); border:1px solid var(--border); color:var(--fg);
  border-radius:10px; padding:9px 12px 9px 34px; width:280px; outline:none; transition:.16s;
  font-family:var(--font); font-size:13px}
#q:focus{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-dim); width:320px}
.kbd{position:absolute; right:9px; top:50%; transform:translateY(-50%); color:var(--mute);
  font:11px var(--mono); border:1px solid var(--border); border-radius:5px; padding:1px 5px; background:var(--bg2)}
select#resume, select#country, select#place, select#workmode, select#funding, select#group{background:var(--card); color:var(--fg); border:1px solid var(--border);
  border-radius:10px; padding:9px 10px; font-size:13px; outline:none; cursor:pointer}
.chk{display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--dim);
  background:var(--card); border:1px solid var(--border); border-radius:10px; padding:8px 10px; cursor:pointer; user-select:none}
.chk input{accent-color:var(--accent); cursor:pointer; margin:0}
.iconbtn{background:var(--card); border:1px solid var(--border); color:var(--dim);
  width:38px;height:38px;border-radius:10px; cursor:pointer; display:grid; place-items:center; transition:.16s}
.iconbtn:hover{border-color:var(--border-h); color:var(--fg)}
/* kpis */
.kpis{display:grid; grid-template-columns:repeat(6,1fr); gap:12px; padding:22px 24px 6px}
.kpi{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  padding:14px 16px; position:relative; overflow:hidden; transition:.18s}
.kpi:hover{border-color:var(--border-h)}
.kpi .lab{color:var(--mute); font-size:11px; text-transform:uppercase; letter-spacing:.08em; font-weight:600}
.kpi .val{font-size:28px; font-weight:680; margin-top:6px; letter-spacing:-.5px}
.kpi .bar{position:absolute; left:0; bottom:0; height:3px; width:100%; opacity:.9;
  background:linear-gradient(90deg,var(--accent),transparent)}
.kpi.s .bar{background:linear-gradient(90deg,var(--strong),transparent)}
.kpi.g .bar{background:linear-gradient(90deg,var(--good),transparent)}
/* chips */
.chips{display:flex; gap:8px; padding:14px 24px 4px; flex-wrap:wrap}
.chip{display:inline-flex; align-items:center; gap:7px; background:var(--card);
  border:1px solid var(--border); color:var(--fg); border-radius:99px; padding:6px 13px;
  cursor:pointer; font-size:13px; transition:.16s; user-select:none}
.chip:hover{border-color:var(--border-h)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--c)}
.chip b{color:var(--dim); font-variant-numeric:tabular-nums; font-weight:600}
.chip.off{opacity:.4}
.chip.off .dot{background:var(--mute)}
/* tabs */
.tabs{display:flex; gap:4px; padding:14px 24px 0; flex-wrap:wrap; border-bottom:1px solid var(--border)}
.tab{background:transparent; border:0; border-bottom:2px solid transparent; color:var(--dim);
  padding:9px 14px; font-size:14px; font-weight:600; cursor:pointer; display:inline-flex; gap:7px;
  align-items:center; transition:.15s; margin-bottom:-1px}
.tab:hover{color:var(--fg)}
.tab.active{color:var(--fg); border-bottom-color:var(--c)}
.tab b{font-variant-numeric:tabular-nums; color:var(--c);
  background:color-mix(in srgb,var(--c) 16%,transparent); padding:0 8px; border-radius:99px; font-size:12px}
/* overview */
#overview{padding:18px 24px 60px}
.view[hidden]{display:none}
.ov-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(258px,1fr)); gap:14px; margin-top:14px}
.panel{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px}
.panel.wide{grid-column:1/-1}
.panel h3{font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--mute); margin:0 0 13px; font-weight:600}
.panel h4{font-size:12px; color:var(--mute); margin:15px 0 8px; font-weight:600}
.donut-wrap{display:flex; gap:20px; align-items:center; flex-wrap:wrap}
.donut{width:132px; height:132px; border-radius:50%; flex:none; display:grid; place-items:center}
.donut .hole{width:96px; height:96px; border-radius:50%; background:var(--card); display:grid; place-items:center; text-align:center}
.donut .hole b{font-size:27px; font-weight:720; letter-spacing:-.5px; line-height:1}
.donut .hole span{font-size:11px; color:var(--mute)}
.legend{display:grid; gap:7px; min-width:120px}
.legend .lg{font-size:13px; color:var(--dim); display:flex; gap:8px; align-items:center}
.legend .lg .dot{width:9px;height:9px;border-radius:3px}
.legend .lg b{color:var(--fg)} .legend .lg i{color:var(--mute); font-style:normal; margin-left:auto}
.frow{display:flex; align-items:center; gap:10px; font-size:13px; color:var(--dim); margin:7px 0}
.frow>span{flex:0 0 148px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.frow b{color:var(--fg); margin-left:auto; font-variant-numeric:tabular-nums}
.fbar{flex:1; height:7px; background:var(--bg2); border-radius:99px; overflow:hidden; min-width:40px}
.fbar i{display:block; height:100%; background:var(--accent)}
.muted{color:var(--mute); font-size:13px; line-height:1.5}
.chips-static{display:flex; gap:6px; flex-wrap:wrap}
.tchip{font-size:12px; background:var(--accent-dim); color:var(--accent); border-radius:99px; padding:3px 11px}
.stack{display:flex; height:10px; border-radius:99px; overflow:hidden; background:var(--bg2)}
.stack i{display:block; height:100%}
.stack-lg{display:flex; gap:12px; flex-wrap:wrap; margin-top:8px}
.stack-lg .lg{font-size:12px; color:var(--dim); display:flex; gap:6px; align-items:center}
.stack-lg .lg .dot{width:8px;height:8px;border-radius:3px} .stack-lg .lg b{color:var(--fg)}
.ovtable{width:100%; border-collapse:collapse; font-size:13px}
.ovtable th{text-align:left; color:var(--mute); font-size:11px; text-transform:uppercase; letter-spacing:.05em;
  padding:7px 10px; border-bottom:1px solid var(--border)}
.ovtable td{padding:9px 10px; border-bottom:1px solid var(--border); color:var(--dim)}
.ovtable tbody tr{cursor:pointer; transition:.12s}
.ovtable tbody tr:hover{background:var(--bg2)}
.ovtable td:nth-child(2){color:var(--fg); font-weight:500}
.tierpill.sm{font-size:11px; padding:2px 8px}
/* list */
main{padding:12px 24px 60px; display:grid; gap:11px}
.job{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  padding:15px 18px; display:grid; grid-template-columns:60px 1fr auto 16px; gap:16px; align-items:center;
  cursor:pointer; transition:transform .16s ease, border-color .16s ease, box-shadow .16s ease;
  animation:rise .4s both}
.job:hover{transform:translateY(-2px); border-color:var(--border-h); box-shadow:var(--shadow)}
.job.blocked{opacity:.5}
.dots{display:flex; gap:12px; margin-top:9px; flex-wrap:wrap}
.dot-i{font-size:12px; color:var(--mute); display:inline-flex; gap:4px; align-items:center}
.chev{color:var(--mute); font-size:22px; line-height:1; transition:.16s}
.job:hover .chev{color:var(--fg); transform:translateX(2px)}
/* detail drawer */
#overlay{position:fixed; inset:0; background:rgba(0,0,0,.5); opacity:0; pointer-events:none;
  transition:opacity .22s; z-index:40; backdrop-filter:blur(2px)}
#overlay.on{opacity:1; pointer-events:auto}
#drawer{position:fixed; top:0; right:0; height:100%; width:min(500px,94vw); z-index:50;
  background:var(--bg2); border-left:1px solid var(--border); box-shadow:-24px 0 60px -20px rgba(0,0,0,.6);
  transform:translateX(100%); transition:transform .26s cubic-bezier(.22,.61,.36,1); overflow-y:auto}
#drawer.on{transform:none}
.dw-head{position:sticky; top:0; z-index:2; padding:20px 22px 16px; border-bottom:1px solid var(--border);
  background:color-mix(in srgb,var(--bg2) 84%,transparent); backdrop-filter:blur(10px)}
.dw-top{display:flex; gap:12px; align-items:flex-start}
.dw-score{font-weight:720; font-size:26px; letter-spacing:-1px; line-height:1}
.dw-title{font-size:16px; font-weight:650; letter-spacing:-.3px}
.dw-co{color:var(--dim); font-size:13px; margin-top:3px}
.dw-close{margin-left:auto; background:var(--card); border:1px solid var(--border); color:var(--dim);
  width:32px; height:32px; border-radius:9px; cursor:pointer; flex:none}
.dw-close:hover{color:var(--fg); border-color:var(--border-h)}
.dw-actions{display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; align-items:center}
.btn{display:inline-flex; align-items:center; gap:6px; padding:8px 14px; border-radius:10px; font-size:13px;
  font-weight:600; text-decoration:none; cursor:pointer; border:1px solid var(--border)}
.btn.primary{background:var(--accent); border-color:var(--accent); color:#fff}
.btn.primary:hover{filter:brightness(1.08)}
.dw-body{padding:18px 22px 48px}
.sec{margin-bottom:20px}
.sec h3{font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--mute); margin:0 0 8px; font-weight:650}
.sec .txt{white-space:pre-wrap; color:var(--dim); font-size:13px; line-height:1.6}
.sec .txt code{background:var(--card); border:1px solid var(--border); border-radius:5px; padding:1px 5px; font:12px var(--mono)}
.kv{font-size:13px; margin:4px 0; color:var(--dim)}
.kv b{color:var(--fg); font-weight:600}
.lnk{display:block; color:var(--dim); font-size:13px; text-decoration:none; padding:7px 0; border-bottom:1px solid var(--border)}
.lnk:hover{color:var(--accent)}
.tag{font:11px var(--mono); color:var(--accent); background:var(--accent-dim); padding:1px 7px; border-radius:6px}
@keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
@media (max-width:820px){.kpis{grid-template-columns:repeat(2,1fr)} #q:focus{width:280px}
  .job{grid-template-columns:48px 1fr auto} .chev{display:none}}
.scorewrap{text-align:center}
.score{font-size:23px; font-weight:720; letter-spacing:-1px; line-height:1}
.sbar{height:3px; border-radius:3px; background:var(--border); margin-top:8px; overflow:hidden}
.sbar>i{display:block; height:100%; border-radius:3px}
.mid{min-width:0}
.title{font-weight:600; font-size:15px; letter-spacing:-.2px}
.title a{text-decoration:none}
.title a:hover{color:var(--accent)}
.co{color:var(--dim); font-size:13px; margin-top:2px; display:flex; gap:8px; align-items:center; flex-wrap:wrap}
.co .base{font:11px var(--mono); color:var(--accent); border:1px solid var(--accent-dim);
  background:var(--accent-dim); padding:1px 7px; border-radius:6px}
.new{font-size:10px; font-weight:700; color:var(--strong); letter-spacing:.05em;
  border:1px solid color-mix(in srgb,var(--strong) 35%,transparent); border-radius:5px; padding:0 5px}
.dupe{font-size:10px; font-weight:700; color:var(--dim); letter-spacing:.02em;
  border:1px solid var(--border-h); border-radius:5px; padding:0 6px}
.gone{font-size:10px; font-weight:700; color:#d14343; letter-spacing:.02em;
  border:1px solid color-mix(in srgb,#d14343 45%,transparent); border-radius:5px; padding:0 6px}
.rscope{font-size:10px; font-weight:700; color:var(--accent); letter-spacing:.02em;
  border:1px solid var(--accent-dim); background:var(--accent-dim); border-radius:5px; padding:0 6px}
.job.closed{opacity:.62}
.job.closed .title{text-decoration:line-through; text-decoration-color:#d14343}
.enr{margin-top:11px; display:flex; gap:7px; flex-wrap:wrap}
.pill{font-size:12px; background:var(--bg2); border:1px solid var(--border); border-radius:8px;
  padding:3px 9px; color:var(--dim); display:inline-flex; gap:5px; align-items:center; transition:.14s}
.pill:hover{border-color:var(--border-h)}
.pill b{color:var(--fg); font-weight:600}
.pill.pos b{color:var(--strong)} .pill.neg b{color:#f43f5e}
.pill a{text-decoration:none}
.rat{color:var(--mute); font-size:12px; margin-top:11px; padding-top:10px; border-top:1px solid var(--border)}
.tierpill{display:inline-flex; align-items:center; gap:7px; font-size:12px; font-weight:600;
  padding:5px 11px; border-radius:99px; background:var(--bg2); border:1px solid var(--border); white-space:nowrap}
.tierpill .dot{width:8px;height:8px;border-radius:50%;background:var(--c)}
.empty{text-align:center; color:var(--mute); padding:80px 20px}
.empty code{background:var(--card); border:1px solid var(--border); border-radius:6px; padding:2px 7px; font:12px var(--mono)}
footer{color:var(--mute); font-size:12px; text-align:center; padding:24px}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
</style></head><body>
<header>
  <div class="brand">
    <div class="logo"></div>
    <div><h1>jobscope</h1><div class="sub"><span class="tnum">__TOTAL__</span> jobs · __GENERATED__</div></div>
  </div>
  <div class="grow"></div>
  <div class="search">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" placeholder="Filter title, company, skill…" spellcheck="false">
    <span class="kbd">/</span>
  </div>
  <select id="resume" hidden><option value="">All resumes</option></select>
  <select id="country" hidden><option value="">All countries</option></select>
  <select id="place" hidden><option value="">All locations</option></select>
  <select id="workmode" hidden><option value="">All modes</option></select>
  <select id="funding" hidden><option value="">All funding</option></select>
  <select id="scopeSel" hidden></select>
  <label class="chk" id="hideclosed-l" title="Hide postings no longer on the company board"><input type="checkbox" id="hideclosed"> Hide taken-down</label>
  <select id="group" title="Group duplicate postings of the same role">
    <option value="on">Group: on</option>
    <option value="off">Group: off</option>
  </select>
  <button class="iconbtn" id="theme" title="Toggle theme">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
  </button>
</header>
<nav class="tabs" id="tabs"></nav>
<section id="overview" class="view"></section>
<main id="list" class="view" hidden></main>
<div id="overlay"></div>
<aside id="drawer" aria-label="Job details"></aside>
<footer>jobscope · local dashboard · your data stays on this machine</footer>
<script>
const DATA = __DATA__;
const OVERVIEW = __OVERVIEW__;
const TIERC = {Strong:'#22c55e',Good:'#3b82f6',Stretch:'#f59e0b',Skip:'#71717a'};
const BARC = ['#7c6cff','#22c55e','#3b82f6','#f59e0b','#71717a','#e879f9'];
const TABS = ['overview','Strong','Good','Stretch','Skip'];
let activeTab = 'overview';
const q = document.getElementById('q'), resumeSel = document.getElementById('resume'), countrySel = document.getElementById('country'), placeSel = document.getElementById('place'), workmodeSel = document.getElementById('workmode'), fundingSel = document.getElementById('funding'), scopeSel = document.getElementById('scopeSel'), groupSel = document.getElementById('group'), hideClosed = document.getElementById('hideclosed');
const esc = s => (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isNew = r => r.first_seen && (Date.now()-Date.parse(r.first_seen) < 864e5);

function counts(items){const c={Strong:0,Good:0,Stretch:0,Skip:0};(items||DATA).forEach(r=>c[r.tier]=(c[r.tier]||0)+1);return c}
function statsFor(items){
  const c=counts(items); let sum=0,scored=0,blocked=0;
  items.forEach(r=>{ if(r.blocked) blocked++; else if(r.score>0){ sum+=r.score; scored++; } });
  return {c, total:items.length, avg:scored?Math.round(sum/scored):0, blocked};
}
function pct(n,t){return t?Math.round(n/t*100):0;}
function tally(arr){const m={}; arr.forEach(x=>m[x]=(m[x]||0)+1); return m;}
function topN(m,n){return Object.entries(m).sort((a,b)=>b[1]-a[1]).slice(0,n);}
function stackBar(m){
  const segs=Object.entries(m).sort((a,b)=>b[1]-a[1]); const tot=segs.reduce((a,kv)=>a+kv[1],0)||1;
  const bar=segs.map(([k,v],i)=>`<i style="width:${v/tot*100}%;background:${BARC[i%BARC.length]}" title="${esc(k)}: ${v}"></i>`).join('');
  const lg=segs.map(([k,v],i)=>`<span class="lg"><span class="dot" style="background:${BARC[i%BARC.length]}"></span>${esc(k)} <b>${v}</b></span>`).join('');
  return `<div class="stack">${bar}</div><div class="stack-lg">${lg}</div>`;
}
function metaDots(r){const e=r.enrich||{}, d=[];
  if(r.funding) d.push('💵 '+r.funding);
  if(r.salary) d.push('💰');
  if(e.stock&&e.stock.ticker) d.push('📈 '+e.stock.ticker);
  else if(e.stock&&e.stock.public===false) d.push('🏦 Private');
  if(e.glassdoor&&e.glassdoor.rating) d.push('⭐ '+e.glassdoor.rating);
  if(e.reddit&&e.reddit.count) d.push('👥 '+(e.reddit.sentiment||''));
  if((r.contacts||[]).length) d.push('🤝 '+r.contacts.length);
  if(e.news&&e.news.length) d.push('📰 '+e.news.length);
  return d.slice(0,5).map(x=>`<span class="dot-i">${esc(String(x))}</span>`).join('');
}
function card(r,i){
  const col=TIERC[r.tier];
  return `<article class="job ${r.blocked?'blocked':''} ${r.status==='closed'?'closed':''}" data-i="${r._i}" style="animation-delay:${Math.min(i*20,360)}ms">
    <div class="scorewrap">
      <div class="score tnum" style="color:${col}">${r.score}</div>
      <div class="sbar"><i style="width:${Math.max(3,Math.min(100,r.score))}%;background:${col}"></i></div>
    </div>
    <div class="mid">
      <div class="title">${esc(r.title)}</div>
      <div class="co"><span>${esc(r.company||'')}</span><span>·</span><span>${esc(r.location||'')}</span>
        ${r.base?`<span class="base">${esc(r.base)}</span>`:''}${isNew(r)?`<span class="new">NEW</span>`:''}${r.remote&&r.remote_scope&&r.remote_scope!=='global'?`<span class="rscope" title="Geo-restricted remote">Remote \u00b7 ${esc(r.remote_scope)}</span>`:''}${r.status==='closed'?`<span class="gone" title="No longer listed on the company board">\u2691 Taken down</span>`:''}${dupeCount(r)>1?`<span class="dupe">×${dupeCount(r)} postings</span>`:''}</div>
      <div class="dots">${metaDots(r)}</div>
    </div>
    <span class="tierpill" style="--c:${col}"><span class="dot"></span>${r.tier}</span>
    <span class="chev">›</span>
  </article>`;
}
function fillSelect(sel, allLabel, values, fmt){
  if(values.length<2){sel.hidden=true; sel.value=''; return;}
  const cur=sel.value; sel.hidden=false;
  sel.innerHTML=`<option value="">${allLabel}</option>`+
    values.map(v=>`<option value="${esc(v)}">${esc(fmt?fmt(v):v)}</option>`).join('');
  sel.value=values.includes(cur)?cur:'';
}
function facetFilters(){
  fillSelect(resumeSel,'All resumes',[...new Set(DATA.map(r=>r.base).filter(Boolean))].sort(),v=>'Resume: '+v);
  fillSelect(countrySel,'All countries',[...new Set(DATA.map(r=>r.country).filter(Boolean))].sort());
  const places=topN(tally(DATA.map(r=>r.place).filter(Boolean)),20).map(p=>p[0]).sort();
  fillSelect(placeSel,'All locations',places);
  const modes=['remote','on-site'].filter(m=>DATA.some(r=>(r.remote?'remote':'on-site')===m));
  fillSelect(workmodeSel,'All modes',modes,v=>v==='remote'?'Remote':'On-site');
  const scopes=[...new Set(DATA.filter(r=>r.remote).map(r=>r.remote_scope).filter(Boolean))].sort();
  fillSelect(scopeSel,'All remote scopes',scopes,v=>v==='global'?'Remote (anywhere)':'Remote in '+v);
  const order=['public','unicorn'];
  fillSelect(fundingSel,'All funding',order.filter(f=>DATA.some(r=>r.funding===f)),v=>'Funding: '+v);
}
function scoped(){
  const term=q.value.trim().toLowerCase(), rez=resumeSel.value, ctry=countrySel.value, fnd=fundingSel.value, pl=placeSel.value, mode=workmodeSel.value, scp=scopeSel.value;
  return DATA.filter(r=>!rez || r.base===rez)
    .filter(r=>!ctry || r.country===ctry)
    .filter(r=>!pl || r.place===pl)
    .filter(r=>!mode || (r.remote?'remote':'on-site')===mode)
    .filter(r=>!scp || r.remote_scope===scp)
    .filter(r=>!fnd || r.funding===fnd)
    .filter(r=>!hideClosed.checked || r.status!=='closed')
    .filter(r=>!term || (r.title+' '+r.company+' '+(r.rationale||'')).toLowerCase().includes(term));
}
function normTitle(t){return (t||'').toLowerCase().replace(/\(.*?\)|\[.*?\]/g,' ').replace(/[^a-z0-9]+/g,' ').trim();}
function dupeCount(r){return (groupSel.value!=='off' && r._members) ? r._members.length : 1;}
function groupItems(items){
  // collapse same company + normalized title into one representative (highest score)
  const map=new Map();
  for(const r of items){
    const key=(r.company||'').toLowerCase().trim()+'|'+normTitle(r.title);
    const g=map.get(key);
    if(!g){ r._members=[r]; map.set(key,r); }
    else { g._members.push(r); if(r.score>g.score){ r._members=g._members; map.set(key,r); } }
  }
  return [...map.values()];
}
function buildTabs(base){
  const c=counts(base);
  document.getElementById('tabs').innerHTML=TABS.map(t=>{
    const lab=t==='overview'?'Overview':t;
    const badge=t==='overview'?'':`<b>${c[t]||0}</b>`;
    const col=t==='overview'?'var(--accent)':TIERC[t];
    return `<button class="tab ${activeTab===t?'active':''}" data-tab="${t}" style="--c:${col}">${lab}${badge}</button>`;
  }).join('');
  document.querySelectorAll('#tabs .tab').forEach(b=>b.onclick=()=>{ activeTab=b.dataset.tab; render(); });
}
function renderOverview(base){
  const st=statsFor(base), c=st.c, total=base.length;
  const closed=DATA.filter(r=>r.status==='closed').length;
  const kpis=[['Total',total],['Strong',c.Strong],['Good',c.Good],['Avg score',st.avg],['Filtered',st.blocked],['Taken down',closed]]
    .map(([l,v])=>`<div class="kpi"><div class="lab">${l}</div><div class="val tnum">${v}</div></div>`).join('');
  const order=['Strong','Good','Stretch','Skip'], dt=order.reduce((a,t)=>a+(c[t]||0),0)||1;
  let acc=0; const segs=order.filter(t=>c[t]).map(t=>{const p=(c[t]||0)/dt*100, s=`${TIERC[t]} ${acc}% ${acc+p}%`; acc+=p; return s;});
  const donut=`<div class="donut" style="background:conic-gradient(${segs.join(',')||'var(--border) 0 100%'})"><div class="hole"><b>${total}</b><span>analyzed</span></div></div>`;
  const legend=order.map(t=>`<div class="lg"><span class="dot" style="background:${TIERC[t]}"></span>${t} <b>${c[t]||0}</b> <i>${pct(c[t]||0,dt)}%</i></div>`).join('');
  const fn=OVERVIEW.funnel||{}, fk=Object.keys(fn), ftot=fk.reduce((a,k)=>a+fn[k],0);
  const funnel=fk.length?fk.map(k=>`<div class="frow"><span>${esc(k)}</span><div class="fbar"><i style="width:${pct(fn[k],ftot)}%"></i></div><b>${fn[k]}</b></div>`).join('')
    :`<div class="muted">No applications tracked yet.<br>Run <code>prep &lt;id&gt;</code> then <code>track</code>.</div>`;
  const rzBar=stackBar(tally(base.map(r=>r.base||'unassigned')));
  const rmBar=stackBar(tally(base.map(r=>r.remote?'remote':'on-site')));
  const topco=topN(tally(base.map(r=>r.company||'\u2014')),7).map(([n,k])=>`<div class="frow"><span>${esc(n)}</span><b>${k}</b></div>`).join('') || '<div class="muted">\u2014</div>';
  const gaps=(OVERVIEW.gaps||[]).length?(OVERVIEW.gaps||[]).slice(0,8).map(g=>`<div class="frow"><span>${esc(g[0])}</span><div class="fbar"><i style="width:${pct(g[1],OVERVIEW.considered||1)}%"></i></div><b>${g[1]}</b></div>`).join('')
    :'<div class="muted">No skill gaps \u2014 your resumes cover the market.</div>';
  const targets=(OVERVIEW.targets||[]).map(t=>`<span class="tchip">${esc(t)}</span>`).join('') || '<span class="muted">\u2014</span>';
  const top=[...base].sort((a,b)=>b.score-a.score).slice(0,10);
  const rows=top.map(r=>`<tr data-i="${r._i}"><td class="tnum" style="color:${TIERC[r.tier]}">${r.score}</td><td>${esc(r.title)}</td><td>${esc(r.company||'')}</td><td><span class="tierpill sm" style="--c:${TIERC[r.tier]}"><span class="dot"></span>${r.tier}</span></td><td>${esc(r.base||'')}</td></tr>`).join('');
  document.getElementById('overview').innerHTML=`
    <div class="kpis">${kpis}</div>
    <div class="ov-grid">
      <div class="panel"><h3>Analyzed</h3><div class="donut-wrap">${donut}<div class="legend">${legend}</div></div></div>
      <div class="panel"><h3>Targeting these roles</h3><div class="chips-static">${targets}</div>
        <h4>By resume</h4>${rzBar}<h4>By location</h4>${rmBar}</div>
      <div class="panel"><h3>Application funnel</h3>${funnel}</div>
      <div class="panel"><h3>Top companies</h3>${topco}</div>
      <div class="panel wide"><h3>Skill gaps that unlock the most matches</h3>${gaps}</div>
    </div>
    <div class="panel wide" style="margin-top:14px"><h3>Top matches</h3>
      <table class="ovtable"><thead><tr><th>Score</th><th>Title</th><th>Company</th><th>Tier</th><th>Resume</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  document.querySelectorAll('.ovtable tbody tr').forEach(tr=>tr.onclick=()=>openDrawer(+tr.dataset.i));
}
function render(){
  const base=scoped();
  buildTabs(base);
  const ov=document.getElementById('overview'), list=document.getElementById('list');
  if(activeTab==='overview'){ list.hidden=true; ov.hidden=false; renderOverview(base); return; }
  ov.hidden=true; list.hidden=false;
  let items=base.filter(r=>r.tier===activeTab);
  if(groupSel.value!=='off') items=groupItems(items);
  items=[...items].sort((a,b)=>b.score-a.score);
  list.innerHTML=items.length?items.map(card).join('')
    :`<div class="empty">No ${activeTab} jobs match.</div>`;
}
const overlay=document.getElementById('overlay'), drawer=document.getElementById('drawer');
function sec(t,html){return html?`<div class="sec"><h3>${t}</h3>${html}</div>`:''}
function openDrawer(i){
  const r=DATA[i]; if(!r) return; const col=TIERC[r.tier], e=r.enrich||{}; let b='';
  b+=sec('Company brief', r.brief?`<div class="txt">${esc(r.brief)}</div>`:'');
  let comp='';
  if(r.salary) comp+=`<div class="kv">Posting: <b>${esc(r.salary)}</b></div>`;
  if(e.comp&&e.comp.levels_fyi) comp+=`<a class="lnk" href="${e.comp.levels_fyi}" target="_blank">Levels.fyi salaries ↗</a>`;
  b+=sec('Compensation', comp);
  if(e.stock&&e.stock.ticker){let s=`<div class="kv"><b>${e.stock.ticker}</b> ${e.stock.price??''} ${e.stock.change_pct!=null?`(${e.stock.change_pct>=0?'+':''}${e.stock.change_pct}%)`:''}</div>`;
    if(e.stock.market_cap) s+=`<div class="kv">Market cap: <b>${e.stock.market_cap}</b></div>`;
    if(e.stock.week52_pos_pct!=null) s+=`<div class="kv">52-wk position: <b>${e.stock.week52_pos_pct}%</b></div>`;
    b+=sec('Stock', s);}
  else if(e.stock&&e.stock.public===false) b+=sec('Stock','<div class="kv">Private / pre-IPO</div>');
  if(e.reddit&&e.reddit.count) b+=sec('Reddit',`<div class="kv">Sentiment <b>${esc(e.reddit.sentiment||'')}</b> · ${e.reddit.count} mentions</div>${e.reddit.summary?`<div class="txt">${esc(e.reddit.summary)}</div>`:''}`);
  if(e.glassdoor&&e.glassdoor.rating) b+=sec('Glassdoor',`<div class="kv">Rating <b>${e.glassdoor.rating}/5</b></div>`);
  if(e.news&&e.news.length) b+=sec('Recent news', e.news.map(n=>`<a class="lnk" href="${n.link||'#'}" target="_blank">${esc(n.title)} ↗</a>`).join(''));
  if((r.contacts||[]).length) b+=sec('Referral leads', r.contacts.map(c=>`<a class="lnk" href="${c.url||'#'}" target="_blank">🤝 ${esc(c.name||'lead')} ↗</a>`).join(''));
  if(r.rationale) b+=sec('Why this rank',`<div class="txt">${esc(r.rationale)}</div>`);
  if(groupSel.value!=='off' && r._members && r._members.length>1){
    const rows=[...r._members].sort((a,b)=>b.score-a.score).map(m=>
      `<a class="lnk" href="${esc(m.url||'#')}" target="_blank">${esc(m.source||'link')} · ${esc(m.location||'\u2014')} · ${m.score} \u2197</a>`).join('');
    b+=sec(`All postings (${r._members.length})`, rows);
  }
  const meta=[r.base?`<span class="tag">${esc(r.base)}</span> base`:'', r.funding?`funding: ${esc(r.funding)}`:'', r.posted?`Posted ${esc(r.posted)}`:''].filter(Boolean).join(' · ');
  drawer.innerHTML=`<div class="dw-head"><div class="dw-top">
      <div class="dw-score" style="color:${col}">${r.score}</div>
      <div><div class="dw-title">${esc(r.title)}</div><div class="dw-co">${esc(r.company||'')} · ${esc(r.location||'')}</div></div>
      <button class="dw-close" title="Close (Esc)">✕</button></div>
      <div class="dw-actions">${r.url?`<a class="btn primary" href="${esc(r.url)}" target="_blank">Open posting ↗</a>`:''}
      <span class="tierpill" style="--c:${col}"><span class="dot"></span>${r.tier}</span></div></div>
    <div class="dw-body">${b||'<div class="txt">No enrichment yet — run <code>enrich</code>.</div>'}
      ${meta?`<div class="sec"><h3>Meta</h3><div class="kv">${meta}</div></div>`:''}</div>`;
  drawer.querySelector('.dw-close').onclick=closeDrawer;
  overlay.classList.add('on'); drawer.classList.add('on');
}
function closeDrawer(){overlay.classList.remove('on'); drawer.classList.remove('on')}
overlay.onclick=closeDrawer;
document.getElementById('list').addEventListener('click',ev=>{const c=ev.target.closest('.job'); if(c)openDrawer(+c.dataset.i)});
document.getElementById('theme').onclick=()=>{
  const h=document.documentElement; h.classList.toggle('light'); h.classList.toggle('dark');
  try{localStorage.setItem('js-theme',h.classList.contains('light')?'light':'dark')}catch(e){}};
try{if(localStorage.getItem('js-theme')==='light'){document.documentElement.classList.remove('dark');document.documentElement.classList.add('light')}}catch(e){}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus()}
  else if(e.key==='Escape'){ if(drawer.classList.contains('on'))closeDrawer();
    else if(document.activeElement===q){q.value='';q.blur();render()} }});
q.oninput=()=>render();
[resumeSel,countrySel,placeSel,workmodeSel,fundingSel,scopeSel,groupSel].forEach(s=>s.onchange=()=>render());
hideClosed.onchange=()=>render();
DATA.forEach((r,i)=>r._i=i);
facetFilters(); render();
</script></body></html>"""
