import json

from jobscope.core.config import RETIRED_SEARCH_KEYS, load_config


def test_legacy_broad_discovery_controls_are_removed_from_effective_config(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps({
            "search": {
                "sites": ["indeed", "linkedin", "google"],
                "proxies": ["user:password@example.test:8080"],
                "hours_old": 24,
                "profiles": [{
                    "name": "remote",
                    "location": "Remote",
                    "proxies": ["proxy.example.test:8080"],
                    "results_wanted": 100,
                }],
            },
            "discovery": {"enabled": True, "interval_hours": 1},
        }),
        encoding="utf-8",
    )

    cfg = load_config(str(legacy))

    assert "discovery" not in cfg
    assert RETIRED_SEARCH_KEYS.isdisjoint(cfg["search"])
    assert RETIRED_SEARCH_KEYS.isdisjoint(cfg["search"]["profiles"][0])