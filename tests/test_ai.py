import copy
import os
import tempfile
import time

import pytest

from jobscope.core import ai
from jobscope.core import config as _config
from jobscope.core.config import DEFAULT_CONFIG
from jobscope.core.store import Store


@pytest.fixture(autouse=True)
def _env_only_secrets(monkeypatch):
    # Keep these tests hermetic: resolve secrets from the environment only, never
    # the developer's OS keychain, so a locally configured key can't flip
    # availability and make the assertions env-dependent.
    monkeypatch.setattr(_config, "_secret", lambda name, default="": os.environ.get(name, default))


def _cfg(**ai_over):
    # Build from DEFAULT_CONFIG (not the on-disk config.yaml) so the tests don't
    # depend on the developer's provider / key / enabled settings.
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["ai"].update(ai_over)
    return cfg


def test_unavailable_when_disabled(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    assert ai.available(_cfg(enabled=False), "company_brief") is False
    assert ai.chat(_cfg(enabled=False), None, "s", "u", purpose="company_brief") is None


def test_local_available_requires_loopback_allowlisted_model_and_no_key(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    assert ai.available(cfg, "company_brief") is True
    cfg["ai"]["base_url"] = "http://192.0.2.10:11434/v1"
    assert ai.available(cfg, "company_brief") is False
    cfg = _cfg(enabled=True, model="unapproved:latest")
    assert ai.available(cfg, "company_brief") is False
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    assert ai.available(_cfg(enabled=True), "company_brief") is False


@pytest.mark.parametrize("base_url", [
    "https://127.0.0.1:11434/v1",
    "http://0.0.0.0:11434/v1",
    "http://ollama:11434/v1",
    "http://127.0.0.1:11434/api",
    "http://127.0.0.1/v1",
    "http://user@127.0.0.1:11434/v1",
    "http://127.0.0.1:11434/v1?target=remote",
])
def test_local_route_rejects_non_exact_urls(monkeypatch, base_url):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    assert ai.available(
        _cfg(enabled=True, base_url=base_url), "company_brief",
    ) is False


def test_chat_caches(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    calls = {"n": 0}

    def fake_post(_cfg, _policy, _body):
        calls["n"] += 1
        return "hello"

    monkeypatch.setattr(ai, "_post", fake_post)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "a.db"))
        a = ai.chat(cfg, store, "sys", "user", purpose="company_brief")
        b = ai.chat(cfg, store, "sys", "user", purpose="company_brief")
        assert a == b == "hello"
        assert calls["n"] == 1
        run = store.conn.execute(
            "SELECT action, count, status FROM runs WHERE action LIKE 'ai:%' "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        assert run["action"].startswith("ai:company_brief:ollama:")
        assert dict(run) == {"action": run["action"], "count": 1, "status": "cache"}
        assert "hello" not in run["action"]
        store.close()


def test_strategy_for_resolves_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    assert ai.strategy_for(cfg, "generative") == "council"
    assert ai.strategy_for(cfg, "classify") == "ensemble"
    assert ai.strategy_for({"quorum": {}}, "generative") is None
    assert ai.strategy_for({}, "generative") is None


def test_chat_passes_strategy_and_context_to_quorum(monkeypatch):
    pytest.importorskip("quorum.api")
    import quorum.api as qapi
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["quorum"]["enabled"] = True
    seen = {}

    def fake_q(cfg, store, system, user, *, temperature=None, strategy=None,
               history=None, context=None):
        seen["strategy"] = strategy
        seen["context"] = context
        return "Q-ANSWER"

    monkeypatch.setattr(qapi, "chat", fake_q)
    out = ai.chat(
        cfg, None, "sys", "user", purpose="company_brief",
        strategy="council",
    )
    assert out is None and seen == {}


def test_chat_never_falls_back_when_quorum_fails(monkeypatch):
    pytest.importorskip("quorum.api")
    import quorum.api as qapi
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["quorum"]["enabled"] = True

    def old_q(cfg, store, system, user, *, temperature=None, history=None, context=None):
        return None  # mimics an older quorum with no strategy= kwarg (raises TypeError first)

    monkeypatch.setattr(qapi, "chat", old_q)
    http_calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: http_calls.append(True) or "SINGLE")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "a.db"))
        out = ai.chat(
            cfg, store, "sys", "user", purpose="company_brief",
            strategy="council",
        )
        assert out is None and http_calls == []
        store.close()


def test_budget_exhaustion_performs_zero_backend_calls(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["ai"]["budget"]["max_calls"] = 1
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") == "ok"
    assert ai.chat(cfg, None, "s", "u2", purpose="company_brief") is None
    assert calls == [True]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_input_chars", 1),
        ("max_input_tokens", 1),
        ("max_output_tokens", 1),
        ("max_fanout", 0),
        ("wall_seconds", 0),
    ],
)
def test_each_budget_dimension_exhausts_before_backend(monkeypatch, field, value):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["ai"]["budget"][field] = value
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "system", "user", purpose="company_brief") is None
    assert calls == []


def test_elapsed_wall_budget_blocks_before_backend(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["ai"]["budget"]["wall_seconds"] = 0.001
    ai.reset_budget(cfg)
    time.sleep(0.002)
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") is None
    assert calls == []


@pytest.mark.parametrize("backend_output", [None, "", 42, "x" * 4001])
def test_backend_or_schema_failures_return_none(monkeypatch, backend_output):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    monkeypatch.setattr(ai, "_post", lambda *_args: backend_output)

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") is None


def test_validator_failure_returns_none(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    monkeypatch.setattr(ai, "_post", lambda *_args: "invented output")

    assert ai.chat(
        cfg, None, "s", "Python role", purpose="company_brief",
        validator=ai.grounded_text_validator("Python role", max_words=5),
    ) is None


def test_remote_route_requires_all_privacy_controls_before_http(monkeypatch):
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    cfg = _cfg(
        enabled=True,
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model-v1",
    )
    cfg["ai"]["remote"] = {
        "enabled": True,
        "purposes": {
            "company_brief": {
                "models": ["vendor/model-v1"],
                "providers": ["provider-a"],
            },
        },
    }
    bodies = []
    monkeypatch.setattr(
        ai, "_post",
        lambda _cfg, _policy, body: bodies.append(body) or "bounded",
    )

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") == "bounded"
    assert bodies[0]["provider"] == {
        "order": ["provider-a"],
        "only": ["provider-a"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
    }
    bodies.clear()
    assert ai.chat(cfg, None, "s", "u", purpose="outreach_draft_advice") is None
    assert bodies == []


@pytest.mark.parametrize(
    ("base_url", "allowed"),
    [
        ("http://127.0.0.1:11434/v1", True),
        ("http://127.0.0.1:11434/v1/", True),
        ("http://localhost:11434/v1", True),
        ("http://[::1]:11434/v1", True),
        ("http://127.0.0.1:11434", False),
        ("http://127.0.0.1:11434/v1/chat", False),
        ("https://127.0.0.1:11434/v1", False),
        ("http://127.0.0.1/v1", False),
        ("http://user:pw@127.0.0.1:11434/v1", False),  # pragma: allowlist secret
        ("http://127.0.0.1:11434/v1?probe=1", False),
        ("http://evil.example:11434/v1", False),
        ("http://127.0.0.1:notaport/v1", False),
    ],
)
def test_local_route_accepts_only_exact_loopback_v1_urls(monkeypatch, base_url, allowed):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)

    assert ai.available(_cfg(enabled=True, base_url=base_url), "company_brief") is allowed


def test_budget_is_shared_across_purposes_within_one_run(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["ai"]["budget"]["max_calls"] = 1
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") == "ok"
    assert ai.chat(cfg, None, "s", "u", purpose="tailor_advice") is None
    assert calls == [True]


def test_cached_output_is_revalidated_before_reuse(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    monkeypatch.setattr(ai, "_post", lambda *_args: "Python role summary")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "a.db"))
        assert ai.chat(
            cfg, store, "s", "Python role", purpose="company_brief",
        ) == "Python role summary"

        ai.reset_budget(cfg)
        monkeypatch.setattr(ai, "_post", lambda *_args: None)
        assert ai.chat(
            cfg, store, "s", "Python role", purpose="company_brief",
            validator=ai.grounded_text_validator("Python role", max_words=2),
        ) is None
        store.close()


def test_chat_refuses_history_or_context_injection(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(
        cfg, None, "s", "u", purpose="company_brief",
        history=[{"role": "user", "content": "x"}],
    ) is None
    assert ai.chat(
        cfg, None, "s", "u", purpose="company_brief",
        context=[{"title": "t", "text": "x"}],
    ) is None
    assert calls == []


def test_purpose_must_be_in_the_local_allowlist(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["ai"]["local_purposes"] = ["company_brief"]

    assert ai.available(cfg, "company_brief") is True
    assert ai.available(cfg, "tailor_advice") is False
    assert ai.available(cfg, "inbox_advice") is False


def test_provenance_is_bounded_and_absent_without_a_route():
    cfg = _cfg(enabled=True)

    assert ai.provenance(cfg, "company_brief") == {
        "purpose": "company_brief",
        "provider": "ollama",
        "model": cfg["ai"]["model"],
        "remote": False,
    }
    assert ai.provenance(cfg, "not_a_purpose") == {}
    assert ai.provenance(_cfg(enabled=False), "company_brief") == {}


@pytest.mark.parametrize("mutation", [
    "remote_off", "wrong_base", "wrong_model", "no_providers", "invalid_provider",
])
def test_remote_policy_mismatch_performs_zero_backend_calls(monkeypatch, mutation):
    monkeypatch.setenv("JOBSCOPE_AI_API_KEY", "k")
    cfg = _cfg(
        enabled=True, provider="openrouter",
        base_url="https://openrouter.ai/api/v1", model="vendor/model-v1",
    )
    cfg["ai"]["remote"] = {
        "enabled": True,
        "purposes": {
            "company_brief": {
                "models": ["vendor/model-v1"],
                "providers": ["provider-a"],
            },
        },
    }
    if mutation == "remote_off":
        cfg["ai"]["remote"]["enabled"] = False
    elif mutation == "wrong_base":
        cfg["ai"]["base_url"] = "https://example.test/v1"
    elif mutation == "wrong_model":
        cfg["ai"]["model"] = "vendor/other"
    elif mutation == "no_providers":
        cfg["ai"]["remote"]["purposes"]["company_brief"]["providers"] = []
    else:
        cfg["ai"]["remote"]["purposes"]["company_brief"]["providers"] = ["bad/provider"]
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") is None
    assert calls == []


def test_hosted_runtime_kill_switch_performs_zero_backend_calls(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    cfg = _cfg(enabled=True)
    cfg["_runtime"] = {"hosted": True}
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *_args: calls.append(True) or "ok")

    assert ai.chat(cfg, None, "s", "u", purpose="company_brief") is None
    assert calls == []

