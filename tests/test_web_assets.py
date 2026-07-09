"""Guards for the React/PWA dashboard asset layer.

These tests inspect source assets instead of running a browser: the important
invariants are that the v2 cockpit stays wired to its dependency-free motion layer
and warm design tokens, and that the encrypted applications shell keeps its static
UI without touching the encrypted payload.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_v2_cockpit_is_wired() -> None:
    pkg = json.loads(_read("web/package.json"))
    # The v2 rebuild dropped the heavy animation deps for a dependency-free native
    # motion layer -- guard against them creeping back in.
    assert "lottie-react" not in pkg["dependencies"]
    assert "motion" not in pkg["dependencies"]

    app = _read("web/src/App.tsx")
    # The whole app is behind the auth gate, rendering the v2 cockpit shell.
    assert "<AuthGate" in app and "<ShellV2" in app

    motion = _read("web/src/ui/motion.ts")
    assert "export function animate" in motion
    assert "export function viewTransition" in motion
    assert "prefers-reduced-motion" in motion

    # The warm light/dark design tokens back the cockpit.
    css = _read("web/src/styles/theme.css")
    for token in ("--paper", "--panel", "--ink", "--brand-coral"):
        assert token in css

    # The four cockpit lenses are present.
    for lens in ("board", "briefing", "triage", "timeline"):
        assert (ROOT / "web" / "src" / "features" / lens).is_dir()


def test_web_v2_board_card_and_auth_gate() -> None:
    board = _read("web/src/features/board/Board.tsx")
    # The Kanban card is a tappable button (opens the drawer) tagged for the
    # staggered entrance animation.
    assert "onOpen" in board and "data-board-card" in board

    gate = _read("web/src/app/AuthGate.tsx")
    # Whole-app auth: an in-browser unlock of the encrypted payload; the lock copy
    # reassures that nothing is sent anywhere.
    assert "unlockDashboard" in gate
    assert "This dashboard is locked" in gate
    assert "Nothing is sent anywhere" in gate


def test_encrypted_applications_shell_keeps_spotlight_without_touching_payload() -> None:
    tpl = _read("scripts/apps-template.html")

    assert "window.__ENC__ = __ENC_BLOB__;" in tpl
    assert "--spot-x" in tpl and "--spot-y" in tpl
    assert "pointermove" in tpl
    assert "status-" in tpl and "status-offer" in tpl
    assert "--status-color" in tpl
    assert "Wrong passphrase." in tpl
