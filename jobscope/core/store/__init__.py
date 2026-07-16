"""SQLite persistence for jobscope.

Follows the threatscope pattern: a single ``SCHEMA`` script, ``sqlite3.Row``
factory, an ``_ensure_columns`` migration hook for additive changes, and an
``now_iso`` helper. One database holds jobs, per-company enrichment, referral
contacts, application tracking, the profile/resume, and the AI response cache.

The implementation is split by concern into this package: :mod:`.base` owns the
single shared connection, the ``SCHEMA`` DDL, and the additive migration, while
each concern is a mixin (:mod:`.jobs`, :mod:`.enrichment`, :mod:`.applications`,
:mod:`.mail`, :mod:`.profile`, :mod:`.meta`). ``Store`` composes them over the
one connection, so the public API is unchanged: ``from jobscope.store import
Store`` and ``from jobscope.store import now_iso`` keep working exactly as before.
"""
from __future__ import annotations

# Re-export the model records that were importable from the old flat module, so
# ``from jobscope.store import Job`` (etc.) keeps working unchanged.
from ..model import Job, MailEvent, Resume
from .applications import ApplicationsMixin
from .base import SCHEMA, _row_to_job, _StoreBase, now_iso
from .enrichment import EnrichmentMixin
from .jobs import JobsMixin
from .mail import MailMixin
from .meta import MetaMixin
from .monitoring import MonitoringMixin
from .profile import ProfileMixin
from .reconciliation_audit import ReconciliationAuditMixin


class Store(JobsMixin, EnrichmentMixin, ApplicationsMixin, MailMixin,
            ProfileMixin, MetaMixin, MonitoringMixin, ReconciliationAuditMixin,
            _StoreBase):
    """One SQLite database behind a single shared connection.

    Composes the per-concern mixins over :class:`~jobscope.store.base._StoreBase`,
    which sets up the connection, applies ``SCHEMA``, and runs the additive
    ``_ensure_columns`` migration. All methods operate on the same ``self.conn``.
    """


__all__ = [
    "Store",
    "now_iso",
    "SCHEMA",
    "_row_to_job",
    "Job",
    "MailEvent",
    "Resume",
]
