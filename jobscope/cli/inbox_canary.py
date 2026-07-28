"""No-send live IMAP canary with an isolated throwaway database."""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Callable

from jobscope.core.store import Store


def run(
    cfg: dict, account: str, *,
    sync: Callable[..., int] | None = None,
    temp_dir_factory: Callable[..., object] = tempfile.TemporaryDirectory,
) -> int:
    email = (account or "").strip()
    if not email:
        raise ValueError("inbox canary requires --account")
    accounts = [
        copy.deepcopy(value)
        for value in ((cfg.get("inbox", {}) or {}).get("accounts") or [])
        if str((value or {}).get("email") or "").strip().casefold() == email.casefold()
    ]
    if len(accounts) != 1:
        raise ValueError("inbox canary account must match exactly one configured account")

    safe_cfg = copy.deepcopy(cfg)
    safe_cfg.setdefault("inbox", {}).update({
        "enabled": True,
        "accounts": accounts,
        "store_snippets": False,
        "include_spam": False,
    })
    safe_cfg.setdefault("email", {})["enabled"] = False
    safe_cfg.setdefault("ai", {})["enabled"] = False
    safe_cfg.setdefault("apply", {}).setdefault("outreach", {})["enabled"] = False

    from jobscope.ingest import inbox
    sync = sync or inbox.run
    with temp_dir_factory(prefix="jobscope-inbox-canary-") as directory:
        db_path = Path(str(directory)) / "canary.db"
        safe_cfg.setdefault("output", {})["db_path"] = str(db_path)
        with Store(str(db_path)) as store:
            result = int(sync(
                safe_cfg, store, dry_run=True, account=email,
                backfill=False, initiator="cli",
            ) or 0)
            if store.mail_events():
                raise RuntimeError("inbox canary wrote mail events")
            markers = store.conn.execute(
                "SELECT key FROM meta WHERE key LIKE 'inbox:%'"
            ).fetchall()
            if markers:
                raise RuntimeError("inbox canary advanced UID markers")
            health = store.source_health(f"inbox:{email}")
            classified = int(health[0]["item_count"] or 0) if health else 0
        if result:
            return result
        if classified < 1:
            raise RuntimeError("inbox canary did not classify the expected benign message")
    print("  inbox canary passed: TLS verified, message classified, mailbox read-only")
    return 0