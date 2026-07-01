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
    rationale = job.rationale or ""
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": ("Remote" if job.is_remote else job.location) or job.location,
        "remote": bool(job.is_remote),
        "url": job.url,
        "score": job.score,
        "tier": job.tier or "Skip",
        "base": job.resume_base or "",
        "salary": salary,
        "industry": job.company_industry,
        "rationale": rationale,
        "blocked": "⛔" in rationale,
        "posted": job.date_posted,
        "first_seen": job.first_seen or "",
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


def _render(rows: list[dict]) -> str:
    data = json.dumps(rows).replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__DATA__", data)
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
select#sort{background:var(--card); color:var(--fg); border:1px solid var(--border);
  border-radius:10px; padding:9px 10px; font-size:13px; outline:none; cursor:pointer}
.iconbtn{background:var(--card); border:1px solid var(--border); color:var(--dim);
  width:38px;height:38px;border-radius:10px; cursor:pointer; display:grid; place-items:center; transition:.16s}
.iconbtn:hover{border-color:var(--border-h); color:var(--fg)}
/* kpis */
.kpis{display:grid; grid-template-columns:repeat(5,1fr); gap:12px; padding:22px 24px 6px}
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
/* list */
main{padding:12px 24px 60px; display:grid; gap:11px}
.job{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  padding:15px 18px; display:grid; grid-template-columns:64px 1fr auto; gap:16px; align-items:start;
  transition:transform .16s ease, border-color .16s ease, box-shadow .16s ease;
  animation:rise .4s both}
.job:hover{transform:translateY(-2px); border-color:var(--border-h); box-shadow:var(--shadow)}
.job.blocked{opacity:.5}
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
@keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
@media (max-width:820px){.kpis{grid-template-columns:repeat(2,1fr)} #q:focus{width:280px} .job{grid-template-columns:52px 1fr}}
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
  <select id="sort">
    <option value="score">Sort: Score</option>
    <option value="new">Sort: Newest</option>
    <option value="company">Sort: Company</option>
  </select>
  <button class="iconbtn" id="theme" title="Toggle theme">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
  </button>
</header>
<section class="kpis" id="kpis"></section>
<section class="chips" id="chips"></section>
<main id="list"></main>
<footer>jobscope · local dashboard · your data stays on this machine</footer>
<script>
const DATA = __DATA__;
const TIERC = {Strong:'#22c55e',Good:'#3b82f6',Stretch:'#f59e0b',Skip:'#71717a'};
const off = new Set(['Skip']);
const q = document.getElementById('q'), sortSel = document.getElementById('sort');
const esc = s => (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isNew = r => r.first_seen && (Date.now()-Date.parse(r.first_seen) < 864e5);

function counts(){const c={Strong:0,Good:0,Stretch:0,Skip:0};DATA.forEach(r=>c[r.tier]=(c[r.tier]||0)+1);return c}
function animate(el,to){const t0=performance.now(),dur=650;
  (function step(t){const k=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k,3);
   el.textContent=Math.round(to*e);if(k<1)requestAnimationFrame(step)})(t0)}
function kpis(){
  const c=counts(), scored=DATA.filter(r=>!r.blocked&&r.score>0);
  const avg=scored.length?scored.reduce((a,r)=>a+r.score,0)/scored.length:0;
  const blocked=DATA.filter(r=>r.blocked).length;
  const cards=[['Total',DATA.length,''],['Strong',c.Strong,'s'],['Good',c.Good,'g'],
    ['Avg score',Math.round(avg),''],['Filtered',blocked,'']];
  document.getElementById('kpis').innerHTML=cards.map(([l,v,cl])=>
    `<div class="kpi ${cl}"><div class="lab">${l}</div><div class="val tnum" data-v="${v}">0</div><div class="bar"></div></div>`).join('');
  document.querySelectorAll('.kpi .val').forEach(el=>animate(el,+el.dataset.v));
}
function chips(){
  const c=counts();
  document.getElementById('chips').innerHTML=['Strong','Good','Stretch','Skip'].map(t=>
    `<button class="chip ${off.has(t)?'off':''}" data-tier="${t}" style="--c:${TIERC[t]}">
       <span class="dot"></span>${t} <b class="tnum">${c[t]||0}</b></button>`).join('');
  document.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{
    const t=ch.dataset.tier; off.has(t)?off.delete(t):off.add(t); ch.classList.toggle('off'); render();});
}
function pills(r){
  let o=''; const e=r.enrich||{};
  if(r.salary) o+=`<span class="pill">💰 <b>${esc(r.salary)}</b></span>`;
  if(e.stock&&e.stock.ticker){const up=(e.stock.change_pct||0)>=0;
    o+=`<span class="pill ${up?'pos':'neg'}">📈 <b>${e.stock.ticker}</b> ${e.stock.price??''}${e.stock.change_pct!=null?` (${up?'+':''}${e.stock.change_pct}%)`:''}</span>`}
  if(e.stock&&e.stock.public===false) o+=`<span class="pill">🏦 Private</span>`;
  if(e.reddit&&e.reddit.sentiment){const neg=/neg/.test(e.reddit.sentiment);
    o+=`<span class="pill ${neg?'neg':''}">👥 <b>${e.reddit.sentiment}</b></span>`}
  if(e.glassdoor&&e.glassdoor.rating) o+=`<span class="pill">⭐ <b>${e.glassdoor.rating}</b></span>`;
  if(e.news&&e.news.length) o+=`<span class="pill">📰 ${e.news.length}</span>`;
  (r.contacts||[]).slice(0,2).forEach(c=>o+=`<span class="pill">🤝 <a href="${c.url||'#'}" target="_blank">${esc(c.name||'lead')}</a></span>`);
  return o;
}
function card(r,i){
  const col=TIERC[r.tier];
  return `<article class="job ${r.blocked?'blocked':''}" style="animation-delay:${Math.min(i*22,400)}ms">
    <div class="scorewrap">
      <div class="score tnum" style="color:${col}">${r.score}</div>
      <div class="sbar"><i style="width:${Math.max(3,Math.min(100,r.score))}%;background:${col}"></i></div>
    </div>
    <div class="mid">
      <div class="title">${r.url?`<a href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</div>
      <div class="co"><span>${esc(r.company||'')}</span><span>·</span><span>${esc(r.location||'')}</span>
        ${r.base?`<span class="base">${esc(r.base)}</span>`:''}${isNew(r)?`<span class="new">NEW</span>`:''}</div>
      <div class="enr">${pills(r)}</div>
      ${r.rationale?`<div class="rat">${esc(r.rationale)}</div>`:''}
    </div>
    <span class="tierpill" style="--c:${col}"><span class="dot"></span>${r.tier}</span>
  </article>`;
}
function render(){
  const term=q.value.trim().toLowerCase(), s=sortSel.value;
  let items=DATA.filter(r=>!off.has(r.tier)).filter(r=>!term ||
    (r.title+' '+r.company+' '+(r.rationale||'')).toLowerCase().includes(term));
  if(s==='company') items=[...items].sort((a,b)=>(a.company||'').localeCompare(b.company||''));
  else if(s==='new') items=[...items].sort((a,b)=>(b.first_seen||'').localeCompare(a.first_seen||''));
  const list=document.getElementById('list');
  list.innerHTML=items.length?items.map(card).join('')
    :`<div class="empty">No matching jobs.<br><br>Run <code>jobscope scan</code> then <code>jobscope match</code>.</div>`;
}
document.getElementById('theme').onclick=()=>{
  const h=document.documentElement; h.classList.toggle('light'); h.classList.toggle('dark');
  try{localStorage.setItem('js-theme',h.classList.contains('light')?'light':'dark')}catch(e){}};
try{if(localStorage.getItem('js-theme')==='light'){document.documentElement.classList.remove('dark');document.documentElement.classList.add('light')}}catch(e){}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus()}
  else if(e.key==='Escape'&&document.activeElement===q){q.value='';q.blur();render()}});
q.oninput=render; sortSel.onchange=render;
kpis(); chips(); render();
</script></body></html>"""
