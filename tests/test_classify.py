"""Unit tests for the optional AI seniority classifier (ai.chat is monkeypatched;
no network)."""
from jobscope import ai, classify
from jobscope.model import Job


def _job():
    return Job(title="Security Engineer", description="own the security paved road")


def test_parse_valid_json(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level": "senior", "required_years": 6}')
    assert classify.classify_seniority({}, None, _job()) == {"level": "senior", "required_years": 6.0}


def test_extracts_json_from_prose(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: 'Sure:\n{"level":"mid","required_years":3}\ndone')
    out = classify.classify_seniority({}, None, _job())
    assert out["level"] == "mid" and out["required_years"] == 3.0


def test_rejects_out_of_vocab(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level": "wizard", "required_years": 4}')
    assert classify.classify_seniority({}, None, _job()) is None


def test_rejects_non_json(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: "I think this is a senior role, honestly.")
    assert classify.classify_seniority({}, None, _job()) is None


def test_clamps_years(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level": "principal", "required_years": 99}')
    assert classify.classify_seniority({}, None, _job())["required_years"] == 20.0


def test_years_fallback_from_level(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level": "senior"}')
    assert classify.classify_seniority({}, None, _job())["required_years"] == 6.0  # rank 3 * 2


def test_none_when_ai_off(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: None)
    assert classify.classify_seniority({}, None, _job()) is None


def test_short_circuits_empty_posting(monkeypatch):
    called = []
    monkeypatch.setattr(ai, "chat", lambda *a, **k: called.append(1) or "{}")
    assert classify.classify_seniority({}, None, Job(title="", description="")) is None
    assert not called


def test_parses_discipline_technical(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k:
                        '{"level":"senior","required_years":6,"discipline":"technical"}')
    out = classify.classify_seniority({}, None, _job())
    assert out["discipline"] == "technical"
    assert out["level"] == "senior" and out["required_years"] == 6.0   # level/years intact


def test_parses_discipline_advisory_case_insensitive(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k:
                        '{"level":"mid","required_years":3,"discipline":"  ADVISORY "}')
    assert classify.classify_seniority({}, None, _job())["discipline"] == "advisory"


def test_discipline_omitted_when_invalid(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k:
                        '{"level":"senior","required_years":6,"discipline":"wizard"}')
    out = classify.classify_seniority({}, None, _job())
    assert "discipline" not in out
    assert out == {"level": "senior", "required_years": 6.0}            # legacy shape kept


def test_discipline_absent_keeps_legacy_shape(monkeypatch):
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level":"staff","required_years":8}')
    out = classify.classify_seniority({}, None, _job())
    assert out == {"level": "staff", "required_years": 8.0}             # no discipline key added
