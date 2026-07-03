"""`jobscope init` - scaffold a working config and data directory.

Non-destructive: never overwrites an existing config or resume. Prints the next
steps a fresh user should take.
"""
from __future__ import annotations

import os
import shutil

from ..core.config import DEFAULT_CONFIG, load_config


def run(args) -> int:
    created = []

    # config.yaml from the committed example (fall back to serialized defaults)
    if not any(os.path.exists(c) for c in ("config.yaml", "config.yml", "config.json")):
        if os.path.exists("config.example.yaml"):
            shutil.copyfile("config.example.yaml", "config.yaml")
        else:
            _write_yaml_defaults("config.yaml")
        created.append("config.yaml")

    cfg = load_config(getattr(args, "config", None))

    # data dir + application package dir
    for d in (
        os.path.dirname(cfg["output"]["db_path"]) or ".",
        cfg["apply"]["package_dir"],
    ):
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            created.append(d + os.sep)

    # .env from example
    if os.path.exists(".env.example") and not os.path.exists(".env"):
        shutil.copyfile(".env.example", ".env")
        created.append(".env")

    if created:
        print("  created: " + ", ".join(created))
    else:
        print("  already initialized (nothing to do)")

    print("\nNext steps:")
    print("  1. Add your resume at data/resume.md (or point profile.resume_path at it)")
    print("  2. Edit config.yaml -> search.terms / search.location")
    print("  3. python -m jobscope resume import data/resume.md")
    print("  4. python -m jobscope scan && python -m jobscope match")
    print("  5. python -m jobscope dashboard --open")
    return 0


def _write_yaml_defaults(path: str) -> None:
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(DEFAULT_CONFIG, fh, sort_keys=False, default_flow_style=False)
    except ImportError:
        import json
        with open(path.replace(".yaml", ".json"), "w", encoding="utf-8") as fh:
            json.dump(DEFAULT_CONFIG, fh, indent=2)
