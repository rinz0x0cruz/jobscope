"""jobscope command-line interface.

Usage:
    python -m jobscope init                       Scaffold config + data dir
    python -m jobscope resume import <path> [--name N]  Parse/store a (named) base resume
    python -m jobscope scan                        Scrape jobs for your searches
    python -m jobscope match                       Score jobs (multi-resume + filters)
    python -m jobscope enrich [--job ID]           Add comp/stock/reddit/news/contacts/brief
    python -m jobscope tailor <job_id>             Tailor resume + cover letter
    python -m jobscope prep <job_id>               Build a review-ready application package
    python -m jobscope apply <job_id> [--assist]   Open the application (human submits)
    python -m jobscope brief <job_id>              Blunt, risk-forward company brief
    python -m jobscope gaps [--top N]              Skill-gap learning plan across your jobs
    python -m jobscope new                          New Strong/Good jobs since last review
    python -m jobscope dashboard [--open]          Render the HTML dashboard
    python -m jobscope serve [--port 8799 --open]  Serve the dashboard locally
    python -m jobscope track [--set job_id=status] Funnel + follow-up reminders
    python -m jobscope inbox [--dry-run]           Sync Gmail (IMAP) -> application funnel
    python -m jobscope export [--format json|csv]  Export ranked jobs
    python -m jobscope purge [--mail --applications --older-than N]  Wipe stored email PII / apps
    python -m jobscope prune [--yes]               Drop stored jobs outside your India/remote scope
    python -m jobscope secrets [set|list|rm|import-env]  Store secrets in the OS keychain
    python -m jobscope selftest                     Offline self-tests (no network)
"""
from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..core.config import load_config
from ..core.store import Store


def _store(args, cfg) -> Store:
    db_path = getattr(args, "db", None) or cfg["output"]["db_path"]
    return Store(db_path)


# --------------------------------------------------------------------------
# commands (feature modules are imported lazily so the core CLI stays light
# and offline-friendly; heavy deps like jobspy/playwright load only on demand)
# --------------------------------------------------------------------------
def cmd_init(args, cfg):
    from . import scaffold
    return scaffold.run(args)


def cmd_resume(args, cfg):
    from ..analyze import resume as _resume
    with _store(args, cfg) as store:
        return _resume.import_resume(args.path, store, cfg, name=getattr(args, "name", "default"))


def cmd_scan(args, cfg):
    from ..ingest import scrape
    with _store(args, cfg) as store:
        return scrape.run(cfg, store)


def cmd_pipeline(args, cfg):
    from . import pipeline
    with _store(args, cfg) as store:
        return pipeline.run(cfg, store, do_prep=not args.no_prep)


def cmd_match(args, cfg):
    from ..analyze import match
    with _store(args, cfg) as store:
        return match.run(cfg, store)


def cmd_enrich(args, cfg):
    from .. import enrich
    with _store(args, cfg) as store:
        return enrich.run(cfg, store, job_id=getattr(args, "job", None))


def cmd_tailor(args, cfg):
    from ..apply import tailor
    with _store(args, cfg) as store:
        return tailor.run(cfg, store, args.job_id)


def cmd_prep(args, cfg):
    from ..apply import apply
    with _store(args, cfg) as store:
        return apply.prep(cfg, store, args.job_id)


def cmd_apply(args, cfg):
    from ..apply import apply
    with _store(args, cfg) as store:
        return apply.apply(cfg, store, args.job_id, assist=args.assist)


def cmd_dashboard(args, cfg):
    from ..deliver import render
    with _store(args, cfg) as store:
        if getattr(args, "emit_json", False):
            path = render.emit_json(cfg, store, public=getattr(args, "public", False))
            print(f"  dashboard json -> {path}")
            return 0
        path = render.build(cfg, store, public=getattr(args, "public", False))
    print(f"  dashboard -> {path}")
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open(f"file://{__import__('os').path.abspath(path)}")
    return 0


def cmd_serve(args, cfg):
    from ..deliver import serve
    return serve.run(cfg, port=args.port, open_browser=args.open)


def cmd_track(args, cfg):
    from ..apply import track
    with _store(args, cfg) as store:
        return track.run(store, set_expr=getattr(args, "set", None), cfg=cfg,
                         timeline=getattr(args, "timeline", None))


def cmd_inbox(args, cfg):
    from ..ingest import inbox
    with _store(args, cfg) as store:
        return inbox.run(cfg, store, dry_run=args.dry_run, account=args.account,
                         since=args.since, backfill=args.backfill)


def cmd_new(args, cfg):
    from ..apply import track
    with _store(args, cfg) as store:
        return track.run_new(store)


def cmd_gaps(args, cfg):
    from ..analyze import insights
    with _store(args, cfg) as store:
        return insights.run(cfg, store, top=args.top)


def cmd_brief(args, cfg):
    from ..apply import brief as _brief
    with _store(args, cfg) as store:
        return _brief.run(cfg, store, args.job_id)


def cmd_export(args, cfg):
    from ..deliver import exporter
    with _store(args, cfg) as store:
        return exporter.run(store, fmt=args.format, out=args.out)


def cmd_selftest(args, cfg):
    from . import selftest
    return selftest.run()


def _secret_names(cfg) -> list[str]:
    """The env-var NAMES this config references for secrets (values are never touched)."""
    names = [
        cfg.get("ai", {}).get("api_key_env", "JOBSCOPE_AI_API_KEY"),
        cfg.get("email", {}).get("password_env", "JOBSCOPE_SMTP_PASSWORD"),
    ]
    for acct in (cfg.get("inbox", {}).get("accounts") or []):
        env = (acct or {}).get("password_env")
        if env:
            names.append(env)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def cmd_secrets(args, cfg):
    """Manage secrets in the OS keychain (keyring). Values are never printed."""
    import os
    try:
        import keyring
    except ImportError:
        print("  keyring is not installed.  pip install keyring", file=sys.stderr)
        return 1
    from ..core.config import KEYRING_SERVICE

    action = getattr(args, "action", "list") or "list"
    if action in ("set", "rm") and not args.name:
        print(f"  usage: jobscope secrets {action} <ENV_VAR_NAME>", file=sys.stderr)
        return 2

    if action == "set":
        import getpass
        val = getpass.getpass(f"  value for {args.name} (input hidden): ")
        if not val:
            print("  aborted (empty value)", file=sys.stderr)
            return 1
        keyring.set_password(KEYRING_SERVICE, args.name, val)
        print(f"  stored {args.name} in the OS keychain")
        return 0

    if action == "rm":
        try:
            keyring.delete_password(KEYRING_SERVICE, args.name)
            print(f"  removed {args.name} from the keychain")
        except Exception:  # noqa: BLE001 - not present / backend quirk
            print(f"  {args.name} was not in the keychain")
        return 0

    if action == "import-env":
        moved = 0
        for name in _secret_names(cfg):
            val = os.environ.get(name)
            if val:
                keyring.set_password(KEYRING_SERVICE, name, val)
                moved += 1
                print(f"  imported {name} -> keychain")
        print(f"  imported {moved} secret(s); you can now delete those lines from .env")
        return 0

    # list (status only -- never values)
    print(f"  secrets [{KEYRING_SERVICE} keychain | environment]:")
    for name in _secret_names(cfg):
        try:
            in_ring = keyring.get_password(KEYRING_SERVICE, name) is not None
        except Exception:  # noqa: BLE001
            in_ring = False
        where = "keychain" if in_ring else ("env/.env" if os.environ.get(name) else "MISSING")
        print(f"    {name:<28} {where}")
    return 0


def cmd_purge(args, cfg):
    """Delete sensitive local data (stored email PII and/or tracked applications)."""
    if not (args.mail or args.applications or args.older_than is not None):
        print("  nothing selected. Use --mail, --applications, and/or --older-than N",
              file=sys.stderr)
        return 2
    with _store(args, cfg) as store:
        if args.mail or args.older_than is not None:
            n = store.purge_mail_events(older_than_days=args.older_than)
            scope = f"older than {args.older_than}d" if args.older_than is not None else "all"
            print(f"  purged {n} stored email event(s) ({scope})")
        if args.applications:
            m = store.purge_applications()
            print(f"  purged {m} tracked application(s)")
    return 0


def cmd_prune(args, cfg):
    """Delete stored jobs outside your geographic scope (home country + eligible remote)."""
    from ..core import geo
    home = cfg["search"].get("home_country", "India")
    with _store(args, cfg) as store:
        jobs = store.jobs(order_by_score=False)
        out = [j for j in jobs if not geo.in_scope(j, home)]
        if not out:
            print(f"  no out-of-scope jobs (home={home}); nothing to prune.")
            return 0
        print(f"  {len(out)} of {len(jobs)} stored jobs are outside scope (home={home}):")
        for j in out[:20]:
            print(f"    - {j.title} @ {j.company or '?'} [{j.location or '?'}]")
        if len(out) > 20:
            print(f"    ... and {len(out) - 20} more")
        if args.dry_run or not args.yes:
            print("  (dry run) re-run with --yes to delete them.")
            return 0
        n = store.delete_jobs([j.id for j in out])
        print(f"  pruned {n} out-of-scope job(s); {len(jobs) - n} remain.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobscope", description="Resume-driven job scout & application prep.")
    p.add_argument("--version", action="version", version=f"jobscope {__version__}")
    p.add_argument("--config", default=None, help="Path to config.yaml/json")
    p.add_argument("--db", default=None, help="Override database path")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Scaffold config + data dir").set_defaults(func=cmd_init)

    sp = sub.add_parser("resume", help="Import your resume")
    sp.add_argument("action", choices=["import"], help="What to do")
    sp.add_argument("path", help="Path to resume (.md/.json/.pdf/.txt)")
    sp.add_argument("--name", default="default",
                    help="Name this base resume (e.g. research, consulting) for multi-resume matching")
    sp.set_defaults(func=cmd_resume)

    sub.add_parser("scan", help="Scrape jobs for your searches").set_defaults(func=cmd_scan)
    sub.add_parser("match", help="Score jobs against your resume").set_defaults(func=cmd_match)

    sp = sub.add_parser("pipeline", help="scan -> match -> enrich -> prep top picks -> digest")
    sp.add_argument("--no-prep", action="store_true", help="stop after enrich (don't build packages)")
    sp.set_defaults(func=cmd_pipeline)

    sp = sub.add_parser("enrich", help="Enrich companies with public intel")
    sp.add_argument("--job", default=None, help="Enrich a single job id (default: top N)")
    sp.set_defaults(func=cmd_enrich)

    sp = sub.add_parser("tailor", help="Tailor resume + cover letter for a job")
    sp.add_argument("job_id")
    sp.set_defaults(func=cmd_tailor)

    sp = sub.add_parser("prep", help="Build a review-ready application package")
    sp.add_argument("job_id")
    sp.set_defaults(func=cmd_prep)

    sp = sub.add_parser("apply", help="Open the application (you click submit)")
    sp.add_argument("job_id")
    sp.add_argument("--assist", action="store_true",
                    help="Assisted fill of a PUBLIC ATS form; stops before submit")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("dashboard", help="Render the HTML dashboard")
    sp.add_argument("--open", action="store_true", help="Open in browser")
    sp.add_argument("--public", action="store_true",
                    help="Render a redacted copy safe for public hosting "
                         "(no referral contacts, application funnel, or search terms)")
    sp.add_argument("--emit-json", action="store_true",
                    help="Write the dashboard data as JSON (data/dashboard[.public].json) "
                         "for the web build, instead of rendering HTML")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("serve", help="Serve the dashboard locally")
    sp.add_argument("--port", type=int, default=8799)
    sp.add_argument("--open", action="store_true")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("track", help="View / update application status")
    sp.add_argument("--set", default=None, help="job_id=status")
    sp.add_argument("--timeline", default=None, metavar="JOB_ID",
                    help="Show the email timeline (mail_events) for an application")
    sp.set_defaults(func=cmd_track)

    sp = sub.add_parser("inbox", help="Sync Gmail (IMAP) for application-status emails")
    sp.add_argument("--account", default=None, help="Only sync this configured email address")
    sp.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="Scan mail since this date (default: incremental / lookback_days on first run)")
    sp.add_argument("--backfill", action="store_true",
                    help="Ignore the incremental marker and rescan lookback_days")
    sp.add_argument("--dry-run", action="store_true", help="Classify and print, but write nothing")
    sp.set_defaults(func=cmd_inbox)

    sub.add_parser("new", help="Show new Strong/Good jobs since your last review").set_defaults(func=cmd_new)

    sp = sub.add_parser("gaps", help="Skill-gap learning plan across your matched jobs")
    sp.add_argument("--top", type=int, default=15)
    sp.set_defaults(func=cmd_gaps)

    sp = sub.add_parser("brief", help="Blunt, risk-forward company brief for a job")
    sp.add_argument("job_id")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("export", help="Export ranked jobs")
    sp.add_argument("--format", choices=["json", "csv"], default="json")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("purge", help="Delete stored email PII / applications from the local DB")
    sp.add_argument("--mail", action="store_true",
                    help="Delete stored email events (recruiter PII + body snippets)")
    sp.add_argument("--applications", action="store_true",
                    help="Delete tracked applications (empties the funnel)")
    sp.add_argument("--older-than", type=int, default=None, metavar="DAYS",
                    help="Only delete stored email events older than DAYS")
    sp.set_defaults(func=cmd_purge)

    sp = sub.add_parser("prune", help="Delete stored jobs outside your India/remote scope")
    sp.add_argument("--yes", action="store_true", help="Actually delete (default: preview only)")
    sp.add_argument("--dry-run", action="store_true", help="Preview only; never delete")
    sp.set_defaults(func=cmd_prune)

    sp = sub.add_parser("secrets", help="Store API keys / app passwords in the OS keychain (keyring)")
    sp.add_argument("action", nargs="?", choices=["set", "list", "rm", "import-env"],
                    default="list", help="set|list|rm|import-env (default: list)")
    sp.add_argument("name", nargs="?", default=None,
                    help="Env-var name (e.g. JOBSCOPE_GMAIL_APP_PW) for set/rm")
    sp.set_defaults(func=cmd_secrets)

    sub.add_parser("selftest", help="Offline self-tests (no network)").set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    try:
        return int(args.func(args, cfg) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
