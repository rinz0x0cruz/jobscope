"""Module entry point: ``python -m jobscope`` (and the ``jobscope`` console script).

The CLI implementation lives in :mod:`jobscope.cli`; this stays a thin shim so
both ``jobscope.__main__:main`` (pyproject console script) and ``python -m
jobscope`` resolve to the same entry point.
"""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
