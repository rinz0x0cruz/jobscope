import pathlib

import yaml

from jobscope.core.config import DEFAULT_CONFIG, _deep_merge, load_config

EXAMPLE_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config.example.yaml"


def test_deep_merge_overrides_leaf_keeps_siblings():
    merged = _deep_merge(DEFAULT_CONFIG, {"search": {"location": "Berlin"}})
    assert merged["search"]["location"] == "Berlin"
    assert merged["search"]["results_wanted"] == DEFAULT_CONFIG["search"]["results_wanted"]


def test_default_weights_sum_to_one():
    assert abs(sum(DEFAULT_CONFIG["match"]["weights"].values()) - 1.0) < 1e-9


def test_load_config_defaults_when_missing():
    cfg = load_config("does-not-exist.yaml")
    assert cfg["ai"]["provider"] == "openrouter"
    assert cfg["ai"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert cfg["output"]["db_path"].endswith(".db")


def test_load_config_is_a_copy():
    cfg = load_config(None)
    cfg["search"]["location"] = "mutated"
    assert DEFAULT_CONFIG["search"]["location"] != "mutated"


# --- P-C config-drift guard ------------------------------------------------
# config.example.yaml must document every key path that DEFAULT_CONFIG defines,
# so the shipped example never silently drifts behind jobscope/config.py.

def _missing_key_paths(default, example, prefix=""):
    """Dotted key paths present in ``default`` but absent from ``example``.

    Compares structure only (keys, not values). Recurses into fixed-key
    sub-maps such as ``match.weights`` / ``match.tiers``, but treats empty
    default maps (free-form, e.g. ``profile.links``) and lists (user-populated
    examples, e.g. ``search.profiles`` / ``inbox.accounts``) as leaves — those
    only require the key itself to be present.
    """
    missing = []
    for key, dval in default.items():
        path = f"{prefix}.{key}" if prefix else key
        if not isinstance(example, dict) or key not in example:
            missing.append(path)
            continue
        if isinstance(dval, dict) and dval:  # recurse only into non-empty maps
            missing.extend(_missing_key_paths(dval, example[key], path))
    return missing


def test_config_example_covers_all_default_keys():
    """Every DEFAULT_CONFIG key path must appear in config.example.yaml."""
    assert EXAMPLE_CONFIG.is_file(), f"missing example config: {EXAMPLE_CONFIG}"
    with open(EXAMPLE_CONFIG, "r", encoding="utf-8") as fh:
        example = yaml.safe_load(fh) or {}
    missing = _missing_key_paths(DEFAULT_CONFIG, example)
    assert not missing, (
        "config.example.yaml is out of sync with DEFAULT_CONFIG in "
        "jobscope/config.py. Add these key path(s) to config.example.yaml:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_config_example_parses_through_load_config():
    """The shipped example must merge cleanly through the real loader."""
    cfg = load_config(str(EXAMPLE_CONFIG))
    assert cfg["ai"]["api_key_env"] == "JOBSCOPE_AI_API_KEY"
    assert cfg["inbox"]["imap_host"] == "imap.gmail.com"
