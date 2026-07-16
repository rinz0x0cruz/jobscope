"""jobscope command-line interface.

Usage:
    python -m jobscope init                       Scaffold config + data dir
    python -m jobscope resume import <path> [--name N]  Parse/store a (named) base resume
    python -m jobscope profile [build|show] [--force]   Editable résumé-derived search profile (drives scan)
    python -m jobscope scan                        Scrape jobs for your searches
    python -m jobscope match                       Score jobs (multi-resume + filters)
    python -m jobscope enrich [--job ID]           Add comp/stock/reddit/news/contacts/brief
    python -m jobscope tailor <job_id>             Tailor resume + cover letter
    python -m jobscope prep <job_id>               Build a review-ready application package
    python -m jobscope apply <job_id> [--assist]   Open the application (human submits)
    python -m jobscope outreach <job_id> [--send]  Draft/send a recruiter outreach + resume
    python -m jobscope brief <job_id>              Blunt, risk-forward company brief
    python -m jobscope atscheck [--job ID]         What an ATS extracts from your resume + warnings
    python -m jobscope coverage <job_id>           Per-requirement JD coverage (responsibilities)
    python -m jobscope gaps [--top N]              Skill-gap learning plan across your jobs
    python -m jobscope new                          New Strong/Good jobs since last review
    python -m jobscope referrals [--job ID]        Referral paths across your pipeline + outreach draft
    python -m jobscope interview <job_id>          Interview-prep sheet (fit, topics, STAR, brief, notes)
    python -m jobscope dashboard [--public]        Emit the dashboard JSON payload
    python -m jobscope serve [--port 8799 --open]  Serve the dashboard locally
    python -m jobscope track [--set job_id=status] Funnel + follow-up reminders
    python -m jobscope applications [audit|recover] Reconciliation history + recovery
    python -m jobscope inbox [--dry-run|--reclassify]  Sync Gmail -> funnel (--reclassify: offline repair)
    python -m jobscope export [--format json|csv]  Export ranked jobs
    python -m jobscope purge [--mail --applications --audit --tombstones]  Explicit data cleanup
    python -m jobscope prune [--yes]               Drop stored jobs outside your India/remote scope
    python -m jobscope secrets [set|list|rm|import-env]  Store secrets in the OS keychain
    python -m jobscope doctor                       Offline operational readiness checks
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


def cmd_profile(args, cfg):
    from ..analyze import profile
    with _store(args, cfg) as store:
        return profile.run(cfg, store, action=getattr(args, "action", "show"),
                           resume_name=getattr(args, "resume", None),
                           name=getattr(args, "name", None),
                           force=getattr(args, "force", False))


def cmd_scout(args, cfg):
    from ..apply import scout
    with _store(args, cfg) as store:
        return scout.run(cfg, store, args.company, provider=getattr(args, "provider", None),
                         slug=getattr(args, "slug", None), save=getattr(args, "save", False),
                         limit=getattr(args, "limit", 20))


def cmd_companies(args, cfg):
    from ..ingest import monitor
    with _store(args, cfg) as store:
        if args.action == "seed":
            return monitor.run_seed(cfg, store, force=getattr(args, "force", False))
        if args.action == "scan":
            return monitor.run_scan(cfg, store, company=getattr(args, "company", None))
        if args.action == "apply":
            from ..apply import monitoring
            if not getattr(args, "actions_file", None):
                print("  --actions-file is required for `companies apply`")
                return 1
            return monitoring.run_actions_file(cfg, store, args.actions_file)
        return monitor.run_list(store, include_removed=getattr(args, "all", False))


def cmd_scan(args, cfg):
    from ..ingest import scrape
    with _store(args, cfg) as store:
        return scrape.run(
            cfg, store, mode=getattr(args, "mode", "all"),
            force_discovery=getattr(args, "force_discovery", False),
        )


def cmd_reviews(args, cfg):
    from ..analyze import review
    with _store(args, cfg) as store:
        if args.action == "sync":
            result = review.sync_reviews(store)
            print(
                f"  review queue: {result['pending_monitored']} monitored, "
                f"{result['pending_discovery']} discovery ({result['created']} new)"
            )
            return 0
        rows = store.list_job_reviews(state=getattr(args, "state", None))
        for row in rows:
            origins = "+".join(row["origins"]) or "unknown"
            print(f"  {row['state']:<9} {origins:<20} {row['job_id']}")
        return 0


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


def cmd_outreach(args, cfg):
    from ..apply import outreach
    with _store(args, cfg) as store:
        return outreach.run(cfg, store, args.job_id, to=getattr(args, "to", None),
                            send=getattr(args, "send", False), force=getattr(args, "force", False))


def cmd_outreach_scan(args, cfg):
    from ..apply import outreach
    with _store(args, cfg) as store:
        stats = outreach.scan_applied_contacts(
            cfg, store, limit=getattr(args, "limit", None),
            fetch=not getattr(args, "no_fetch", False))
    print(f"  outreach scan: discovered {stats['discovered']} compan(ies), "
          f"skipped {stats['skipped']} still-fresh.")
    return 0


def cmd_apply(args, cfg):
    from ..apply import apply
    with _store(args, cfg) as store:
        return apply.apply(cfg, store, args.job_id, assist=args.assist)


def cmd_dashboard(args, cfg):
    from ..deliver import render
    with _store(args, cfg) as store:
        path = render.emit_json(cfg, store, public=getattr(args, "public", False))
        web = render.emit_web(cfg, store) if getattr(args, "emit_web", False) else None
    print(f"  dashboard json -> {path}")
    if getattr(args, "emit_web", False):
        print(f"  web dashboard  -> {web}" if web
              else "  web dashboard  -> skipped (web/src/data not found)")
    if getattr(args, "open", False):
        print("  view the dashboard with `jobscope serve`")
    return 0


def cmd_serve(args, cfg):
    from ..deliver import serve
    return serve.run(cfg, port=args.port, open_browser=args.open)


def cmd_refresh(args, cfg):
    from ..deliver import serve
    res = serve.perform_refresh(cfg, force=args.force, full_scan=args.full_scan,
                                on_step=lambda name, message: print(f"  {message}"))
    print(f"  {res['message']}")
    return 0


def cmd_track(args, cfg):
    from ..apply import track
    with _store(args, cfg) as store:
        return track.run(store, set_expr=getattr(args, "set", None), cfg=cfg,
                         timeline=getattr(args, "timeline", None))


def cmd_applications(args, cfg):
    with _store(args, cfg) as store:
        if args.action == "audit":
            run_id = getattr(args, "run_id", None)
            try:
                runs = ([store.get_reconciliation_run(run_id)] if run_id else
                        store.reconciliation_runs(limit=args.limit))
            except ValueError as exc:
                print(f"  {exc}", file=sys.stderr)
                return 2
            for run in runs:
                after = run["applications_after"]
                count_change = f"{run['applications_before']} -> {after if after is not None else '?'}"
                print(
                    f"  {run['started_at']} {run['action']:<10} {run['status']:<9} "
                    f"applications {count_change}; tombstoned {run['tombstoned_count']}; "
                    f"restored {run['restored_count']}"
                )
            if run_id:
                for decision in store.reconciliation_decisions(run_id, limit=args.limit):
                    print(
                        f"    {decision['sequence']:04d} {decision['decision_type']} "
                        f"{decision['reason_code']} {decision['application_id']}"
                    )
            recoverable = store.recoverable_applications(limit=args.limit)
            print(f"  {len(recoverable)} recoverable application(s)")
            for application in recoverable:
                print(
                    f"    {application['status']:<10} {application['job_id']} "
                    f"[{application['tombstone_reason']}]"
                )
            return 0

        if not args.job_id:
            print("  job_id is required for `applications recover`", file=sys.stderr)
            return 2
        application = store.get_application(args.job_id, include_tombstoned=True)
        if application is None or not application.get("tombstoned_at"):
            print("  application is not recoverable")
            return 0
        terminal_statuses = {"rejected", "offer", "withdrawn", "closed"}
        if application.get("status") in terminal_statuses and not args.yes:
            print(
                "  terminal application restore requires --yes confirmation",
                file=sys.stderr,
            )
            return 2
        from ..apply import recovery
        result = recovery.restore_application(store, args.job_id, initiator="cli")
        print("  application restored and marked reconciliation-exempt"
              if result["restored"] else "  application was already active")
        return 0


def cmd_inbox(args, cfg):
    from ..ingest import inbox
    if getattr(args, "include_spam", False):
        cfg.setdefault("inbox", {})["include_spam"] = True
    with _store(args, cfg) as store:
        return inbox.run(cfg, store, dry_run=args.dry_run, account=args.account,
                         since=args.since, backfill=args.backfill,
                         reclassify=getattr(args, "reclassify", False),
                         initiator=getattr(args, "initiator", "cli"))


def cmd_new(args, cfg):
    from ..apply import track
    with _store(args, cfg) as store:
        if getattr(args, "email", False):
            n = track.send_digest(cfg, store)
            print(f"  emailed a digest of {n} new match(es)." if n
                  else "  no digest sent (nothing new, or email disabled).")
            return 0
        return track.run_new(store)


def cmd_referrals(args, cfg):
    from ..apply import referrals
    with _store(args, cfg) as store:
        return referrals.run(cfg, store, job_id=getattr(args, "job", None),
                             discover=getattr(args, "discover", False), top=args.top)


def cmd_interview(args, cfg):
    from ..apply import interview
    with _store(args, cfg) as store:
        return interview.run(cfg, store, args.job_id, note=getattr(args, "note", None),
                             resume_name=getattr(args, "resume", None))


def cmd_gaps(args, cfg):
    from ..analyze import insights
    with _store(args, cfg) as store:
        return insights.run(cfg, store, top=args.top)


def cmd_brief(args, cfg):
    from ..apply import brief as _brief
    with _store(args, cfg) as store:
        return _brief.run(cfg, store, args.job_id)


def cmd_atscheck(args, cfg):
    from ..analyze import atscheck
    with _store(args, cfg) as store:
        return atscheck.run(cfg, store, resume_name=getattr(args, "resume", None),
                            job_id=getattr(args, "job", None))


def cmd_coverage(args, cfg):
    from ..analyze import coverage
    with _store(args, cfg) as store:
        return coverage.run(cfg, store, args.job_id, resume_name=getattr(args, "resume", None))


def cmd_export(args, cfg):
    from ..deliver import exporter
    with _store(args, cfg) as store:
        return exporter.run(store, fmt=args.format, out=args.out)


def cmd_selftest(args, cfg):
    from . import selftest
    return selftest.run()


def cmd_doctor(args, cfg):
    from . import doctor
    return doctor.run(cfg)


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
    audit = bool(getattr(args, "audit", False))
    tombstones = bool(getattr(args, "tombstones", False))
    mail = bool(args.mail or (args.older_than is not None and not audit and not tombstones))
    if not (mail or args.applications or audit or tombstones):
        print("  nothing selected. Use --mail, --applications, --audit, --tombstones, "
              "and/or --older-than N",
              file=sys.stderr)
        return 2
    if tombstones and not getattr(args, "yes", False):
        print("  permanent tombstone purge requires --yes confirmation", file=sys.stderr)
        return 2
    audit_days = args.older_than
    if audit and audit_days is None:
        audit_days = int((cfg.get("retention", {}) or {}).get(
            "reconciliation_audit_days", 730,
        ) or 730)
    with _store(args, cfg) as store:
        if mail:
            n = store.purge_mail_events(older_than_days=args.older_than)
            scope = f"older than {args.older_than}d" if args.older_than is not None else "all"
            print(f"  purged {n} stored email event(s) ({scope})")
        if args.applications:
            m = store.purge_applications()
            print(f"  purged {m} active application(s); tombstones retained")
        if audit:
            decisions = store.purge_reconciliation_decisions(audit_days)
            print(
                f"  purged {decisions} reconciliation decision(s) older than "
                f"{audit_days}d; run summaries and tombstones retained"
            )
        if tombstones:
            removed = store.purge_application_tombstones(args.older_than)
            print(f"  permanently purged {removed} application tombstone(s)")
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

    sp = sub.add_parser("profile",
                        help="Manage résumé-derived search profiles that drive scan (build/show/list/use)")
    sp.add_argument("action", nargs="?", choices=["build", "show", "list", "use"], default="show",
                    help="build (from a résumé), show (default), list all, or use <name> to switch")
    sp.add_argument("name", nargs="?", default=None,
                    help="Profile name -- the target for `use`, or a name for `build`")
    sp.add_argument("--resume", default=None, metavar="NAME",
                    help="Which base résumé to build from (default: your primary)")
    sp.add_argument("--force", action="store_true",
                    help="Overwrite an existing profile when building")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("scout",
                        help="Scout a company's ATS board (Greenhouse/Lever/Ashby) and rank openings vs your active profile")
    sp.add_argument("company", help="Company name (or 'Name|provider|slug' to force a board)")
    sp.add_argument("--provider", default=None, help="ATS provider: greenhouse | lever | ashby")
    sp.add_argument("--slug", default=None, help="Board slug (skips name resolution)")
    sp.add_argument("--save", action="store_true", help="Save matching openings into your pipeline")
    sp.add_argument("--limit", type=int, default=20, help="Max openings to show (default 20)")
    sp.set_defaults(func=cmd_scout)

    sp = sub.add_parser("companies", help="Manage persistent company monitors")
    sp.add_argument("action", nargs="?", choices=["seed", "list", "scan", "apply"], default="list",
                    help="seed, list (default), scan, or apply a validated action file")
    sp.add_argument("company", nargs="?", default=None,
                    help="Company name or monitor id for `scan` (default: all active)")
    sp.add_argument("--force", action="store_true",
                    help="Reimport config/application companies after the initial seed")
    sp.add_argument("--all", action="store_true", help="Include soft-removed monitors in list")
    sp.add_argument("--actions-file", default=None,
                    help="JSON action file for `companies apply` (used by cloud refresh)")
    sp.set_defaults(func=cmd_companies)

    sp = sub.add_parser("scan", help="Scan monitored portals and/or broad discovery sources")
    sp.add_argument("--mode", choices=["all", "monitored", "discovery"], default="all",
                    help="all (default), monitored portals only, or broad discovery only")
    sp.add_argument("--force-discovery", action="store_true",
                    help="Ignore the broad-discovery interval marker")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("reviews", help="Synchronize or inspect the curated review queue")
    sp.add_argument("action", nargs="?", choices=["sync", "list"], default="list")
    sp.add_argument("--state", choices=["pending", "saved", "dismissed"], default=None)
    sp.set_defaults(func=cmd_reviews)
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

    sp = sub.add_parser("outreach", help="Draft (and optionally send) a recruiter outreach email + resume")
    sp.add_argument("job_id")
    sp.add_argument("--to", default=None, help="Send to this exact address (skips discovery)")
    sp.add_argument("--send", action="store_true", help="Actually send via SMTP + record (default: preview only)")
    sp.add_argument("--force", action="store_true", help="Override cooldown / dedup / low-confidence guards")
    sp.set_defaults(func=cmd_outreach)

    sp = sub.add_parser("outreach-scan",
                        help="Pre-compute HR contacts for your active applications (for the dashboard)")
    sp.add_argument("--limit", type=int, default=None,
                    help="Max companies to scan (default: apply.outreach.applied_scan.limit)")
    sp.add_argument("--no-fetch", action="store_true",
                    help="Skip network discovery -- use only inbox recruiters + role inboxes")
    sp.set_defaults(func=cmd_outreach_scan)

    sp = sub.add_parser("dashboard", help="Emit the dashboard JSON payload the web app consumes")
    sp.add_argument("--public", action="store_true",
                    help="Emit the redacted public payload "
                         "(no referral contacts, application funnel, or search terms)")
    sp.add_argument("--emit-json", action="store_true",
                    help="(default now) kept for compatibility with the publish scripts")
    sp.add_argument("--emit-web", action="store_true",
                    help="Also mirror the un-redacted payload to web/src/data/dashboard.json "
                         "(what the local web dev server / npm build reads)")
    sp.add_argument("--open", action="store_true",
                    help="(deprecated) view the dashboard with `jobscope serve`")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("serve", help="Serve the dashboard locally")
    sp.add_argument("--port", type=int, default=8799)
    sp.add_argument("--open", action="store_true")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("refresh",
                        help="Sync Gmail + rescore + rebuild + publish (once-per-day guard)")
    sp.add_argument("--force", action="store_true",
                    help="Run even if already refreshed today")
    sp.add_argument("--full-scan", action="store_true",
                    help="Also re-scrape job boards before matching (slower, 429-prone)")
    sp.set_defaults(func=cmd_refresh)

    sp = sub.add_parser("track", help="View / update application status")
    sp.add_argument("--set", default=None, help="job_id=status")
    sp.add_argument("--timeline", default=None, metavar="JOB_ID",
                    help="Show the email timeline (mail_events) for an application")
    sp.set_defaults(func=cmd_track)

    sp = sub.add_parser("applications", help="Inspect reconciliation audit or recover a tombstone")
    sp.add_argument("action", choices=["audit", "recover"])
    sp.add_argument("job_id", nargs="?", default=None,
                    help="Tombstoned application ID for recover")
    sp.add_argument("--run", dest="run_id", default=None,
                    help="Show controlled decisions for one audit run")
    sp.add_argument("--limit", type=int, default=20,
                    help="Maximum runs, decisions, or recoverable rows to show")
    sp.add_argument("--yes", action="store_true",
                    help="Confirm recovery of a rejected/terminal application")
    sp.set_defaults(func=cmd_applications)

    sp = sub.add_parser("inbox", help="Sync Gmail (IMAP) for application-status emails")
    sp.add_argument("--account", default=None, help="Only sync this configured email address")
    sp.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="Scan mail since this date (default: incremental / lookback_days on first run)")
    sp.add_argument("--backfill", action="store_true",
                    help="Ignore the incremental marker and rescan lookback_days")
    sp.add_argument("--include-spam", action="store_true",
                    help="Also sweep the Gmail spam/junk folder this run (overrides inbox.include_spam)")
    sp.add_argument("--reclassify", action="store_true",
                    help="Offline: re-check stored mail with the current rules + rebuild the funnel "
                         "(instance-split; no Gmail sync)")
    sp.add_argument("--dry-run", action="store_true", help="Classify and print, but write nothing")
    sp.add_argument("--initiator", choices=["cli", "local_refresh", "cloud_refresh"],
                    default="cli", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_inbox)

    sp = sub.add_parser("new", help="Show new Strong/Good jobs since your last review")
    sp.add_argument("--email", action="store_true",
                    help="Email a digest of new matches (needs email.enabled) instead of printing")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("referrals",
                        help="Surface referral paths (contacts) across your pipeline + outreach draft")
    sp.add_argument("--job", default=None, metavar="JOB_ID",
                    help="Referral paths for one job's company (the moment-of-applying view)")
    sp.add_argument("--discover", action="store_true",
                    help="Fetch fresh leads for that company if none are stored (network)")
    sp.add_argument("--top", type=int, default=25, help="Max companies in the pipeline digest")
    sp.set_defaults(func=cmd_referrals)

    sp = sub.add_parser("interview",
                        help="Interview-prep sheet for a job (fit, topics, STAR bank, brief, contacts, notes)")
    sp.add_argument("job_id")
    sp.add_argument("--note", default=None, metavar="TEXT",
                    help="Append a date-stamped note to this application")
    sp.add_argument("--resume", default=None, metavar="NAME",
                    help="Which named base resume to prep against (default: the one that scored the job)")
    sp.set_defaults(func=cmd_interview)

    sp = sub.add_parser("gaps", help="Skill-gap learning plan across your matched jobs")
    sp.add_argument("--top", type=int, default=15)
    sp.set_defaults(func=cmd_gaps)

    sp = sub.add_parser("brief", help="Blunt, risk-forward company brief for a job")
    sp.add_argument("job_id")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("atscheck",
                        help="Show what an ATS extracts from your resume + formatting warnings")
    sp.add_argument("--resume", default=None, metavar="NAME",
                    help="Which named base resume to check (default: your primary)")
    sp.add_argument("--job", default=None, metavar="JOB_ID",
                    help="Also show JD keyword coverage against this job")
    sp.set_defaults(func=cmd_atscheck)

    sp = sub.add_parser("coverage",
                        help="Per-requirement JD coverage report (responsibilities, not just keywords)")
    sp.add_argument("job_id")
    sp.add_argument("--resume", default=None, metavar="NAME",
                    help="Which named base resume to assess (default: the one that scored this job)")
    sp.set_defaults(func=cmd_coverage)

    sp = sub.add_parser("export", help="Export ranked jobs")
    sp.add_argument("--format", choices=["json", "csv"], default="json")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("purge", help="Delete stored email PII / applications from the local DB")
    sp.add_argument("--mail", action="store_true",
                    help="Delete stored email events (recruiter PII + body snippets)")
    sp.add_argument("--applications", action="store_true",
                    help="Delete tracked applications (empties the funnel)")
    sp.add_argument("--audit", action="store_true",
                    help="Delete old reconciliation decisions; retain summaries and tombstones")
    sp.add_argument("--tombstones", action="store_true",
                    help="Permanently delete recoverable application tombstones")
    sp.add_argument("--yes", action="store_true",
                    help="Confirm irreversible tombstone deletion")
    sp.add_argument("--older-than", type=int, default=None, metavar="DAYS",
                    help="Only delete selected email/audit details older than DAYS")
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

    sub.add_parser("doctor", help="Offline operational readiness checks").set_defaults(func=cmd_doctor)
    sub.add_parser("selftest", help="Offline self-tests (no network)").set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    # A --db override is authoritative for the whole run, so sibling paths derived
    # from it (e.g. the search profile at <db-dir>/profile.yaml) stay consistent.
    if getattr(args, "db", None):
        cfg.setdefault("output", {})["db_path"] = args.db
    try:
        return int(args.func(args, cfg) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
