"""Guards for the React/PWA dashboard asset layer.

These tests intentionally inspect source assets instead of running a browser:
the animation layer is visual, but the important invariants are that the public
build keeps its self-contained assets wired and the encrypted applications shell
keeps its static UI enhancements without touching the encrypted payload.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_dashboard_animation_assets_are_wired() -> None:
    pkg = json.loads(_read("web/package.json"))
    assert "lottie-react" in pkg["dependencies"]

    app = _read("web/src/App.tsx")
    header = _read("web/src/components/Header.tsx")
    lottie = _read("web/src/components/SignalLottie.tsx")
    hero = _read("web/src/components/HeroBackdrop.tsx")
    overview = _read("web/src/components/overview/Overview.tsx")
    skill_graph = _read("web/src/components/overview/SkillConstellation.tsx")
    spotlight = _read("web/src/lib/spotlight.ts")
    css = _read("web/src/styles/theme.css")

    # The hero backdrop is a swappable generative canvas (it replaced the retired
    # sakura tree) and is the single ambient layer (the aurora blob + CRT scanlines
    # were retired in the UX overhaul's P0 for a calmer console).
    assert "<HeroBackdrop" in app
    assert "<SignalLottie" in header
    assert "useLottie" in lottie and "jobscope signal" in lottie
    assert "js-signal-glyph" in lottie
    assert "HERO_VARIANTS" in hero and "getContext" in hero
    assert "prefers-reduced-motion" in hero
    assert "<SkillConstellation" in overview
    assert "js-skill-graph" in skill_graph and "js-skill-node" in skill_graph
    assert "role=\"button\"" in skill_graph and "onSelect" in skill_graph
    assert "Select a node to show roles" in overview and "rowMentionsSkill" in overview
    assert "trackSpotlight" in spotlight and "--spot-x" in spotlight and "--spot-y" in spotlight

    for marker in (
        ".js-logo-mark",
        ".js-neon-title",
        ".js-signal-field",
        ".js-hero-aurora",
        ".js-spotlight-card",
        ".js-status-card",
        ".js-skill-graph",
        ".js-skill-node",
        "@keyframes jsAuroraA",
    ):
        assert marker in css


def test_react_cards_use_spotlight_and_status_accents() -> None:
    kpis = _read("web/src/components/Kpis.tsx")
    job_card = _read("web/src/components/JobCard.tsx")
    applications = _read("web/src/components/applications/Applications.tsx")
    app_card = _read("web/src/components/applications/AppCard.tsx")

    assert "onPointerMove={trackSpotlight}" in kpis
    assert "onPointerMove={trackSpotlight}" in job_card
    # The view switcher moved the board's rows into AppCard; the Applications
    # shell keeps its own spotlight Card wrapper, and each AppCard spotlights too.
    assert "onPointerMove={trackSpotlight}" in applications
    assert "onPointerMove={trackSpotlight}" in app_card
    assert "js-status-card" in app_card
    assert "js-status-rail" in app_card
    assert "--status-color" in app_card


def test_encrypted_applications_shell_keeps_spotlight_without_touching_payload() -> None:
    tpl = _read("scripts/apps-template.html")

    assert "window.__ENC__ = __ENC_BLOB__;" in tpl
    assert "--spot-x" in tpl and "--spot-y" in tpl
    assert "pointermove" in tpl
    assert "status-" in tpl and "status-offer" in tpl
    assert "--status-color" in tpl
    assert "Wrong passphrase." in tpl
