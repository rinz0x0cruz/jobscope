"""Company brief -- deliberately blunt, risk-forward, no marketing fluff.

Deterministic by default: a compact fact sheet built from the enrichment we
already gathered plus job-level red flags (ghost-job signals, clearance/visa
barriers). Optional AI rewrite is instructed to stay skeptical and factual --
NO flattery, NO hype -- and to use only the provided facts.
"""
from __future__ import annotations

from typing import Any

from .. import ai
from ..match import clearance_flags, ghost_flags, no_sponsorship


def build(cfg: dict, store, company: str, job, enr: dict) -> dict[str, Any]:
    facts, risks = _facts_and_risks(job, enr)
    text = _ai_brief(cfg, store, company, job, facts, risks) or _deterministic(facts, risks)
    return {"text": text, "facts": facts, "risks": risks, "ai": bool(ai.available(cfg))}


def _facts_and_risks(job, enr: dict) -> tuple[list[str], list[str]]:
    enr = enr or {}
    facts: list[str] = []
    risks: list[str] = []

    stock = enr.get("stock") or {}
    if stock.get("ticker"):
        line = f"Public ({stock['ticker']}) at {stock.get('price', '?')} {stock.get('currency', '')}"
        if stock.get("change_pct") is not None:
            line += f", {stock['change_pct']}% today"
        if stock.get("market_cap"):
            line += f", mkt cap {stock['market_cap']}"
        facts.append(line)
        pos = stock.get("week52_pos_pct")
        if isinstance(pos, (int, float)) and pos <= 25:
            risks.append(f"Stock near 52-week low ({pos}% of range) -- possible headwinds")
    elif stock.get("public") is False:
        facts.append("Private / pre-IPO (no public financials; liquidity/comp less transparent)")

    comp = enr.get("comp") or {}
    if comp.get("range"):
        facts.append(f"Posted comp: {comp['range']}")
    else:
        risks.append("No salary disclosed in the posting")

    gd = enr.get("glassdoor") or {}
    if gd.get("rating") is not None:
        facts.append(f"Glassdoor rating: {gd['rating']}/5")
        if gd["rating"] < 3.3:
            risks.append(f"Below-average Glassdoor rating ({gd['rating']}/5)")

    reddit = enr.get("reddit") or {}
    if reddit.get("count"):
        facts.append(f"Reddit: {reddit['count']} mentions, sentiment {reddit.get('sentiment', '?')}")
        if reddit.get("sentiment") in ("negative", "mixed"):
            risks.append(f"Reddit sentiment is {reddit['sentiment']}")

    news = enr.get("news") or []
    if news:
        facts.append(f"Recent news: \"{news[0]['title']}\"")
        neg = [n for n in news if any(w in n["title"].lower()
               for w in ("layoff", "lawsuit", "breach", "cuts", "shutdown", "resign", "probe"))]
        if neg:
            risks.append(f"Negative headline: \"{neg[0]['title']}\"")

    # job-level red flags
    if ghost_flags(job):
        risks.append("Ghost/low-quality posting signals: " + "; ".join(ghost_flags(job)))
    cf = clearance_flags(job)
    if cf:
        risks.append(f"US clearance/citizenship barrier ({cf[0]})")
    if no_sponsorship(job):
        risks.append("States it will not sponsor a visa")

    if not facts:
        facts.append("Limited public data available")
    return facts, risks


def _deterministic(facts: list[str], risks: list[str]) -> str:
    lines = ["Facts:"]
    lines += [f"- {f}" for f in facts]
    lines.append("Risks / unknowns:")
    lines += [f"- {r}" for r in risks] if risks else ["- none detected from available data"]
    return "\n".join(lines)


def _ai_brief(cfg, store, company, job, facts, risks):
    system = (
        "You are a blunt, skeptical career analyst writing a company brief for a job seeker. "
        "Rules: NO marketing language, NO flattery, NO hype adjectives (no 'exciting', "
        "'innovative', 'leading', etc.). Lead with risks, red flags, and unknowns. Be terse and "
        "factual. Use ONLY the facts provided -- do not invent, infer, or speculate beyond them. "
        "If the data is thin, say so plainly. Output 4-6 short bullet points."
    )
    user = (
        f"Company: {company}\nRole: {job.title}\n"
        "FACTS:\n- " + "\n- ".join(facts) + "\n"
        "RISKS/UNKNOWNS:\n- " + ("\n- ".join(risks) if risks else "none detected")
    )
    return ai.chat(cfg, store, system, user)
