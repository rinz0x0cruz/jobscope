import os
import tempfile

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
