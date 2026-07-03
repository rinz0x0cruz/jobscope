import os
import tempfile

import pytest

from jobscope.core import ai
from jobscope.core.config import load_config
from jobscope.core.store import Store


def _cfg(**ai_over):
    cfg = load_config(None)
    cfg["ai"].update(ai_over)
    return cfg


def test_unavailable_when_disabled(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    assert ai.available(_cfg(enabled=False)) is False
    assert ai.chat(_cfg(enabled=False), None, "s", "u") is None


def test_available_requires_key_except_ollama(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    assert ai.available(_cfg(enabled=True, provider="groq")) is False
    assert ai.available(_cfg(enabled=True, provider="ollama")) is True
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    assert ai.available(_cfg(enabled=True, provider="groq")) is True


def test_chat_caches(monkeypatch):
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    cfg = _cfg(enabled=True, provider="groq")
    calls = {"n": 0}

    def fake_post(_cfg, _body):
        calls["n"] += 1
        return "hello"

    monkeypatch.setattr(ai, "_post", fake_post)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "a.db"))
        a = ai.chat(cfg, store, "sys", "user")
        b = ai.chat(cfg, store, "sys", "user")   # same key -> cached
        assert a == b == "hello"
        assert calls["n"] == 1
        store.close()


def test_strategy_for_resolves_config():
    cfg = load_config(None)
    assert ai.strategy_for(cfg, "generative") == "council"
    assert ai.strategy_for(cfg, "classify") == "ensemble"
    assert ai.strategy_for({"quorum": {}}, "generative") is None
    assert ai.strategy_for({}, "generative") is None


def test_chat_passes_strategy_and_context_to_quorum(monkeypatch):
    pytest.importorskip("quorum.api")
    import quorum.api as qapi
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    cfg = _cfg(enabled=True, provider="groq")
    seen = {}

    def fake_q(cfg, store, system, user, *, temperature=None, strategy=None,
               history=None, context=None):
        seen["strategy"] = strategy
        seen["context"] = context
        return "Q-ANSWER"

    monkeypatch.setattr(qapi, "chat", fake_q)
    out = ai.chat(cfg, None, "sys", "user", strategy="council",
                  context=[{"title": "d", "text": "x"}])
    assert out == "Q-ANSWER"
    assert seen["strategy"] == "council"
    assert seen["context"] == [{"title": "d", "text": "x"}]


def test_chat_falls_back_when_quorum_lacks_strategy(monkeypatch):
    pytest.importorskip("quorum.api")
    import quorum.api as qapi
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    cfg = _cfg(enabled=True, provider="groq")

    def old_q(cfg, store, system, user, *, temperature=None, history=None, context=None):
        return None  # mimics an older quorum with no strategy= kwarg (raises TypeError first)

    monkeypatch.setattr(qapi, "chat", old_q)
    monkeypatch.setattr(ai, "_post", lambda _c, _b: "SINGLE")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "a.db"))
        out = ai.chat(cfg, store, "sys", "user", strategy="council")
        assert out == "SINGLE"  # TypeError retry -> None -> single-model fallback
        store.close()
