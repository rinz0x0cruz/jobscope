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
    python -m jobscope export [--format json|csv]  Export ranked jobs
    python -m jobscope selftest                     Offline self-tests (no network)
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config
from .store import Store


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
    from . import resume as _resume
    with _store(args, cfg) as store:
        return _resume.import_resume(args.path, store, cfg, name=getattr(args, "name", "default"))


def cmd_scan(args, cfg):
    from . import scrape
    with _store(args, cfg) as store:
        return scrape.run(cfg, store)


def cmd_pipeline(args, cfg):
    from . import pipeline
    with _store(args, cfg) as store:
        return pipeline.run(cfg, store, do_prep=not args.no_prep)


def cmd_match(args, cfg):
    from . import match
    with _store(args, cfg) as store:
        return match.run(cfg, store)


def cmd_enrich(args, cfg):
    from . import enrich
    with _store(args, cfg) as store:
        return enrich.run(cfg, store, job_id=getattr(args, "job", None))


def cmd_tailor(args, cfg):
    from . import tailor
    with _store(args, cfg) as store:
        return tailor.run(cfg, store, args.job_id)


def cmd_prep(args, cfg):
    from . import apply
    with _store(args, cfg) as store:
        return apply.prep(cfg, store, args.job_id)


def cmd_apply(args, cfg):
    from . import apply
    with _store(args, cfg) as store:
        return apply.apply(cfg, store, args.job_id, assist=args.assist)


def cmd_dashboard(args, cfg):
    from . import render
    with _store(args, cfg) as store:
        path = render.build(cfg, store, public=getattr(args, "public", False))
    print(f"  dashboard -> {path}")
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open(f"file://{__import__('os').path.abspath(path)}")
    return 0


def cmd_serve(args, cfg):
    from . import serve
    return serve.run(cfg, port=args.port, open_browser=args.open)


def cmd_track(args, cfg):
    from . import track
    with _store(args, cfg) as store:
        return track.run(store, set_expr=getattr(args, "set", None), cfg=cfg)


def cmd_new(args, cfg):
    from . import track
    with _store(args, cfg) as store:
        return track.run_new(store)


def cmd_gaps(args, cfg):
    from . import insights
    with _store(args, cfg) as store:
        return insights.run(cfg, store, top=args.top)


def cmd_brief(args, cfg):
    from . import brief as _brief
    with _store(args, cfg) as store:
        return _brief.run(cfg, store, args.job_id)


def cmd_export(args, cfg):
    from . import exporter
    with _store(args, cfg) as store:
        return exporter.run(store, fmt=args.format, out=args.out)


def cmd_selftest(args, cfg):
    from . import selftest
    return selftest.run()


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
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("serve", help="Serve the dashboard locally")
    sp.add_argument("--port", type=int, default=8799)
    sp.add_argument("--open", action="store_true")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("track", help="View / update application status")
    sp.add_argument("--set", default=None, help="job_id=status")
    sp.set_defaults(func=cmd_track)

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
