from jobscope.config import DEFAULT_CONFIG, _deep_merge, load_config


def test_deep_merge_overrides_leaf_keeps_siblings():
    merged = _deep_merge(DEFAULT_CONFIG, {"search": {"location": "Berlin"}})
    assert merged["search"]["location"] == "Berlin"
    assert merged["search"]["results_wanted"] == DEFAULT_CONFIG["search"]["results_wanted"]


def test_default_weights_sum_to_one():
    assert abs(sum(DEFAULT_CONFIG["match"]["weights"].values()) - 1.0) < 1e-9


def test_load_config_defaults_when_missing():
    cfg = load_config("does-not-exist.yaml")
    assert cfg["ai"]["provider"] == "groq"
    assert cfg["output"]["db_path"].endswith(".db")


def test_load_config_is_a_copy():
    cfg = load_config(None)
    cfg["search"]["location"] = "mutated"
    assert DEFAULT_CONFIG["search"]["location"] != "mutated"
