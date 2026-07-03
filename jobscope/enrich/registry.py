"""Enrichment source registry -- self-registration for intel sources.

Replaces the hardcoded ``if cfg[...]: sections[...] = X.enrich(...)`` ladder in
the coordinator with a tiny decorator. A new *section* intel source is now added
by writing one module and decorating its enricher with ``@source(...)``, instead
of editing ``enrich/__init__.py``.

Each registered entry records:
  * ``section``    -- the stored/emitted section name (a ``store.save_enrichment``
                      kwarg, e.g. ``"comp"``); may differ from the config toggle.
  * ``config_key`` -- the ``enrich.<key>`` toggle that gates the source (e.g.
                      ``"compensation"`` gates the ``"comp"`` section).
  * ``fn``         -- the public enricher (its name/signature stay untouched).
  * ``call``       -- an adapter ``(fn, ctx) -> result`` bridging the shared
                      per-company context to each source's own signature (some
                      need the job, some the configured news feeds).

The decorator returns ``fn`` unchanged -- registration is a pure import-time side
effect -- so ``comp.enrich``, ``stock.enrich``, ... keep their exact public API
and the existing direct-call tests keep working. This module imports only the
stdlib, so the sources can ``from .registry import source`` with no circular
import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

#: Adapter that invokes a source's function from the shared per-company context.
Adapter = Callable[[Callable[..., Any], "EnrichContext"], Any]


@dataclass(frozen=True)
class EnrichContext:
    """The per-company inputs a section source may need for one enrichment."""
    company: str
    job: Any
    ecfg: dict


@dataclass(frozen=True)
class Source:
    """A registered section enricher (saved as ``save_enrichment(<section>=...)``)."""
    section: str
    config_key: str
    fn: Callable[..., Any]
    call: Adapter


#: All registered section sources, in import (registration) order.
SECTION_SOURCES: list[Source] = []


def _by_company(fn: Callable[..., Any], ctx: "EnrichContext") -> Any:
    """Default adapter -- fits the ``enrich(company)`` sources (stock/reddit/glassdoor)."""
    return fn(ctx.company)


def source(*, section: str, config_key: str, call: Optional[Adapter] = None):
    """Register a section enricher so the coordinator can iterate it.

    Args:
        section: stored/emitted section name (the ``save_enrichment`` kwarg).
        config_key: the ``enrich.<key>`` toggle that gates this source.
        call: adapter ``(fn, ctx) -> result`` matching the source's own
            signature; defaults to ``fn(ctx.company)``.

    Returns the decorated function unchanged (registration is a side effect), so
    the source keeps its exact public name and signature.
    """
    invoke = call or _by_company

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        SECTION_SOURCES.append(
            Source(section=section, config_key=config_key, fn=fn, call=invoke)
        )
        return fn

    return deco
