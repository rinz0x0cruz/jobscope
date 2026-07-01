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

from .store import now_iso

TIER_COLORS = {"Strong": "#16a34a", "Good": "#2563eb", "Stretch": "#d97706", "Skip": "#6b7280"}


def build(cfg: dict, store) -> str:
    jobs = store.jobs(order_by_score=True)
    rows = []
    for j in jobs:
        enr = store.get_enrichment(j.company) if j.company else {}
        rows.append(_job_record(j, enr, store))
    path = cfg["output"]["dashboard_path"]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    htmltext = _render(rows)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(htmltext)
    return path


def _job_record(job, enr: dict, store) -> dict[str, Any]:
    salary = _fmt_salary(job)
    contacts = store.contacts_for(job.company) if job.company else []
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": ("Remote" if job.is_remote else job.location) or job.location,
        "url": job.url,
        "score": job.score,
        "tier": job.tier or "Skip",
        "salary": salary,
        "industry": job.company_industry,
        "rationale": job.rationale,
        "posted": job.date_posted,
        "enrich": _enrich_summary(enr),
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


def _render(rows: list[dict]) -> str:
    data = json.dumps(rows).replace("</", "<\\/")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    chips = "".join(
        f'<button class="chip" data-tier="{t}" style="--c:{TIER_COLORS[t]}">'
        f'{t} <b>{counts.get(t, 0)}</b></button>'
        for t in ("Strong", "Good", "Stretch", "Skip")
    )
    return _TEMPLATE.replace("__CHIPS__", chips).replace("__DATA__", data).replace(
        "__GENERATED__", html.escape(now_iso())
    ).replace("__TOTAL__", str(len(rows)))


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>jobscope</title>
<style>
:root{--bg:#0b0f14;--card:#141b23;--fg:#e6edf3;--mut:#93a1b0;--line:#233240}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0;letter-spacing:.5px}
.sub{color:var(--mut);font-size:12px}
.chips{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}
.chip{background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:20px;padding:5px 12px;cursor:pointer;border-left:3px solid var(--c)}
.chip.off{opacity:.35}
#q{background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:8px 12px;width:260px}
main{padding:18px 22px;display:grid;gap:12px}
.job{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.job .top{display:flex;gap:12px;align-items:baseline}
.score{font-weight:700;font-size:20px;min-width:52px}
.title{font-weight:600}
.title a{color:var(--fg);text-decoration:none}
.title a:hover{text-decoration:underline}
.co{color:var(--mut)}
.tier{margin-left:auto;font-size:11px;padding:2px 10px;border-radius:20px;color:#fff}
.meta{color:var(--mut);font-size:12px;margin-top:4px;display:flex;gap:14px;flex-wrap:wrap}
.rat{color:var(--mut);font-size:12px;margin-top:8px;border-top:1px dashed var(--line);padding-top:8px}
.enr{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}
.pill{font-size:11px;background:#0e1620;border:1px solid var(--line);border-radius:8px;padding:3px 8px;color:var(--mut)}
.pill b{color:var(--fg)}
.empty{color:var(--mut);text-align:center;padding:40px}
</style></head><body>
<header>
  <div><h1>jobscope</h1><div class="sub">__TOTAL__ jobs · generated __GENERATED__</div></div>
  <input id="q" placeholder="filter title / company / skill…">
  <div class="chips">__CHIPS__</div>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
const off = new Set();
const q = document.getElementById('q');
const TIERC = {Strong:'#16a34a',Good:'#2563eb',Stretch:'#d97706',Skip:'#6b7280'};
function salaryPill(r){return r.salary?`<span class="pill">💰 <b>${r.salary}</b></span>`:''}
function enrichPills(e){let o='';if(!e)return o;
  if(e.stock&&e.stock.ticker){o+=`<span class="pill">📈 <b>${e.stock.ticker}</b> ${e.stock.price??''} ${e.stock.change_pct!=null?'('+e.stock.change_pct+'%)':''}</span>`}
  if(e.stock&&e.stock.public===false){o+=`<span class="pill">🏦 Private</span>`}
  if(e.reddit&&e.reddit.sentiment){o+=`<span class="pill">👥 reddit: <b>${e.reddit.sentiment}</b></span>`}
  if(e.glassdoor&&e.glassdoor.rating){o+=`<span class="pill">⭐ <b>${e.glassdoor.rating}</b></span>`}
  if(e.news&&e.news.length){o+=`<span class="pill">📰 ${e.news.length} recent</span>`}
  return o}
function contactPills(cs){return (cs||[]).slice(0,3).map(c=>`<span class="pill">🤝 <a href="${c.url||'#'}" target="_blank" style="color:inherit">${c.name||'lead'}</a></span>`).join('')}
function render(){
  const term=q.value.toLowerCase();
  const list=document.getElementById('list');
  const items=DATA.filter(r=>!off.has(r.tier)).filter(r=>{
    if(!term)return true;
    return (r.title+' '+r.company+' '+(r.rationale||'')).toLowerCase().includes(term)});
  if(!items.length){list.innerHTML='<div class="empty">No jobs. Run <code>scan</code> then <code>match</code>.</div>';return}
  list.innerHTML=items.map(r=>`
    <div class="job">
      <div class="top">
        <div class="score" style="color:${TIERC[r.tier]}">${r.score}</div>
        <div>
          <div class="title">${r.url?`<a href="${r.url}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</div>
          <div class="co">${esc(r.company)} · ${esc(r.location||'')}</div>
        </div>
        <span class="tier" style="background:${TIERC[r.tier]}">${r.tier}</span>
      </div>
      <div class="enr">${salaryPill(r)}${enrichPills(r.enrich)}${contactPills(r.contacts)}</div>
      ${r.rationale?`<div class="rat">${esc(r.rationale)}</div>`:''}
    </div>`).join('');
}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
document.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{
  const t=ch.dataset.tier; if(off.has(t)){off.delete(t);ch.classList.remove('off')}else{off.add(t);ch.classList.add('off')} render()});
q.oninput=render; render();
</script></body></html>"""
