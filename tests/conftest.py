"""Shared pytest fixtures.

Keep the suite hermetic. jobscope resolves secrets keychain-first
(``config._secret``: OS keychain -> environment). On a developer machine that has a
real provider key stored, the AI-gated tests would otherwise reach a live model --
slow, flaky, and dependent on local config. Resolve secrets from the environment
only during tests; a test that needs a key present sets it via ``monkeypatch.setenv``.
"""
import os

import pytest

from jobscope.core import config as _config


@pytest.fixture(autouse=True)
def _env_only_secrets(monkeypatch):
    monkeypatch.setattr(_config, "_secret", lambda name, default="": os.environ.get(name, default))
