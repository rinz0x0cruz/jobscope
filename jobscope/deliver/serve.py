"""Serve the jobscope web dashboard (the React SPA) over local HTTP with
localhost-only mutation and refresh APIs.

`jobscope serve` serves the built SPA from ``web/dist`` on 127.0.0.1 (building it
first, un-redacted, if it is missing). The React Scan Gmail control POSTs to
``/api/refresh``; the server then syncs the
Gmail inbox (last ``serve.inbox_days`` days, append-only), rescores matches,
publishes the redacted/encrypted public site, and rebuilds the local un-redacted
SPA -- at most once per day unless forced. The endpoints bind to loopback and are
CSRF-guarded (loopback Origin + a per-run token).
"""
from __future__ import annotations

import datetime as _dt
import base64
import binascii
import http.server
import json
import os
import secrets
import tempfile
import threading
import webbrowser
from dataclasses import asdict, dataclass
from typing import Callable

# Single-process refresh state, shared between the request threads and the
# background worker. Writes are small dict.update() calls (atomic under the GIL);
# _LOCK only guards the "is one already running?" decision in do_POST.
_LOCK = threading.Lock()
_MAX_RESUME_BYTES = 5 * 1024 * 1024
_MAX_RESUME_REQUEST_BYTES = 7 * 1024 * 1024
_RESUME_EXTENSIONS = frozenset({".md", ".txt", ".json", ".pdf"})
_STATE: dict[str, str] = {
    "state": "idle",     # idle | running | done | skipped | error | busy
    "step": "",          # scan | inbox | match | render | publish | ...
    "message": "",
    "started": "",
    "finished": "",
    "last_date": "",     # YYYY-MM-DD of the last successful refresh
}


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    required: bool
    status: str
    detail: str = ""


def _run_stage(name: str, *, required: bool, action: Callable[[], object],
               nonzero_is_failure: bool = False) -> StageResult:
    try:
        value = action()
        if nonzero_is_failure and value not in (0, None):
            raise RuntimeError(f"returned nonzero status {value}")
        detail = str(value) if value not in (None, 0, "") else ""
        return StageResult(name, required, "ok", detail)
    except Exception as exc:
        if required:
            raise RuntimeError(f"required stage '{name}' failed: {exc}") from exc
        return StageResult(name, required, "degraded", str(exc)[:300])


def _require_digest(result) -> int:
    if not result.sent:
        raise RuntimeError(result.detail)
    return result.attempted


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return _dt.date.today().isoformat()


def _repo_root() -> str:
    # .../<root>/jobscope/deliver/serve.py -> <root>
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dist_dir(cfg: dict) -> str:
    """Directory of the built SPA to serve. ``serve.web_dist`` overrides the
    default ``<repo>/web/dist`` (used by tests to point at a fixture)."""
    override = (cfg.get("serve", {}) or {}).get("web_dist")
    return os.path.abspath(override) if override else os.path.join(_repo_root(), "web", "dist")


def _build_server(cfg: dict, port: int):
    """Build (but do not start) the SPA HTTP server with the refresh API wired
    in. Serves ``web/dist`` (building it once, un-redacted, if absent); the React
    shell owns Gmail/refresh controls. Returns ``(httpd, page, token,
    refresh_enabled)``; exposed so tests can drive the endpoints on an ephemeral
    port."""
    from jobscope.core.store import Store

    directory = _dist_dir(cfg)
    serve_cfg = cfg.get("serve", {}) or {}
    refresh_on = bool(serve_cfg.get("refresh_enabled", True))

    build_on_start = bool(serve_cfg.get("build_on_start", False))
    if build_on_start or not os.path.exists(os.path.join(directory, "index.html")):
        with Store(cfg["output"]["db_path"]) as store:
            _build_local_spa(cfg, store)
    with Store(cfg["output"]["db_path"]) as store:
        _STATE["last_date"] = store.meta_get("refresh:last_date", "") or ""

    token = secrets.token_hex(16)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, *args):  # keep the console quiet
            pass

        # -- helpers ------------------------------------------------------
        def _send_json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_index(self) -> None:
            try:
                with open(os.path.join(directory, "index.html"), "rb") as fh:
                    html = fh.read()
            except OSError:
                self.send_error(404, "dashboard not built")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)

        def _authorized(self) -> bool:
            # CSRF/loopback guard: reject any cross-origin caller (Origin whose
            # hostname is not a loopback address), and require the per-run token
            # that only the same-origin page can read via /api/token (a
            # cross-origin site cannot read that response).
            origin = self.headers.get("Origin")
            if origin:
                hostname = origin.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0].lower()
                if hostname not in ("127.0.0.1", "localhost", "[::1]", "::1"):
                    return False
            return self.headers.get("X-Refresh-Token") == token

        def _outreach(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            job_id = str(data.get("job_id") or "").strip()
            if not job_id:
                self._send_json(400, {"ok": False, "error": "job_id required"})
                return
            try:
                from jobscope.apply import outreach
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    if data.get("send"):
                        res = outreach.api_send(
                            cfg, store, job_id, to=str(data.get("to") or ""),
                            subject=str(data.get("subject") or ""),
                            body=str(data.get("body") or ""), force=bool(data.get("force")))
                    else:
                        res = outreach.api_preview(cfg, store, job_id, to=(data.get("to") or None),
                                                   followup=bool(data.get("followup")))
                self._send_json(200, res)
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _company_outreach(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            company = str(data.get("company") or "").strip()
            url = str(data.get("url") or "").strip()
            if not company and not url:
                self._send_json(400, {"ok": False, "error": "company or url required"})
                return
            try:
                from jobscope.apply import outreach
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    if data.get("send"):
                        res = outreach.api_company_send(
                            cfg, store, company, to=str(data.get("to") or ""),
                            subject=str(data.get("subject") or ""),
                            body=str(data.get("body") or ""), url=url,
                            force=bool(data.get("force")))
                    else:
                        res = outreach.api_company_preview(
                            cfg, store, company, url=url, to=(data.get("to") or None))
                self._send_json(200, res)
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _application_update(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            job_id = str(data.get("job_id") or "").strip()
            if not job_id:
                self._send_json(400, {"ok": False, "error": "job_id required"})
                return
            try:
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    store.set_offer(
                        job_id,
                        interview_at=str(data.get("interview_at") or ""),
                        salary_offered=str(data.get("salary_offered") or ""),
                        offer_accepted=str(data.get("offer_accepted") or ""))
                    app = store.get_application(job_id) or {}
                self._send_json(200, {"ok": True, "updated": {
                    "job_id": job_id,
                    "interview_at": app.get("interview_at") or "",
                    "salary_offered": app.get("salary_offered") or "",
                    "offer_accepted": app.get("offer_accepted") or "",
                }})
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _profile_use(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            name = str(data.get("name") or "").strip()
            if not name:
                self._send_json(400, {"ok": False, "error": "name required"})
                return
            try:
                from jobscope.analyze import profile as _profile
                from jobscope.core.store import Store
                from jobscope.deliver import render
                if not _profile.set_active(cfg, name):
                    self._send_json(404, {"ok": False, "error": f"no profile named '{name}'"})
                    return
                with Store(cfg["output"]["db_path"]) as store:
                    prof = render._profile_data(cfg, store)
                self._send_json(200, {"ok": True, "profile": prof})
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _resume_upload(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_RESUME_REQUEST_BYTES:
                self._send_json(413, {"ok": False, "error": "resume upload is too large"})
                return
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send_json(400, {"ok": False, "error": "invalid JSON"})
                return
            filename = os.path.basename(str(data.get("filename") or "").strip())
            requested_name = str(data.get("name") or "").strip()
            extension = os.path.splitext(filename)[1].lower()
            if not requested_name:
                self._send_json(400, {"ok": False, "error": "profile name required"})
                return
            if extension not in _RESUME_EXTENSIONS:
                self._send_json(400, {"ok": False, "error": "resume must be .md, .txt, .json, or .pdf"})
                return
            try:
                content = base64.b64decode(str(data.get("content_base64") or ""), validate=True)
            except (ValueError, binascii.Error):
                self._send_json(400, {"ok": False, "error": "invalid resume encoding"})
                return
            if not content or len(content) > _MAX_RESUME_BYTES:
                self._send_json(413, {"ok": False, "error": "resume must be between 1 byte and 5 MB"})
                return

            path = ""
            try:
                from jobscope.analyze import profile as _profile
                from jobscope.analyze import resume as _resume
                from jobscope.core.model import slugify
                from jobscope.core.store import Store
                from jobscope.deliver import render

                name = slugify(requested_name)[:40]
                if not _profile.can_create_profile(cfg, name):
                    self._send_json(409, {
                        "ok": False,
                        "error": f"profile limit reached ({_profile.MAX_PROFILES})",
                    })
                    return
                with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as handle:
                    handle.write(content)
                    path = handle.name
                with Store(cfg["output"]["db_path"]) as store:
                    if _resume.import_resume(path, store, cfg, name=name) != 0:
                        self._send_json(400, {"ok": False, "error": "could not import resume"})
                        return
                    uploaded = store.get_resume(name)
                    if uploaded is not None:
                        uploaded.source_path = filename
                        store.save_resume(uploaded, name=name)
                    if _profile.run(
                        cfg, store, action="build", resume_name=name,
                        name=name, force=True,
                    ) != 0 or not _profile.set_active(cfg, name):
                        self._send_json(500, {"ok": False, "error": "could not build profile"})
                        return
                    prof = render._profile_data(cfg, store)
                self._send_json(200, {
                    "ok": True,
                    "profile": prof,
                    "profile_count": len(_profile.list_profiles(cfg)),
                    "profile_limit": _profile.MAX_PROFILES,
                })
            except (Exception, SystemExit) as exc:  # surface parser failures without stopping serve
                self._send_json(400, {"ok": False, "error": str(exc)[:200]})
            finally:
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        def _scout(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            company = str(data.get("company") or "").strip()
            if not company:
                self._send_json(400, {"ok": False, "error": "company required"})
                return
            try:
                from jobscope.apply import scout as _scout
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    res = _scout.scout(
                        cfg, store, company,
                        provider=(data.get("provider") or None),
                        slug=(data.get("slug") or None),
                        save=bool(data.get("save")),
                        limit=int(data.get("limit") or 40))
                self._send_json(200, res)
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _company_resolve(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            try:
                from jobscope.apply import monitoring
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    result = monitoring.resolve_company(
                        cfg, store,
                        company=data.get("company") or "",
                        careers_url=data.get("careers_url") or "",
                        provider=data.get("provider") or "",
                        slug=data.get("slug") or "",
                    )
                self._send_json(200, result)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)[:200]})
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        def _monitoring_actions(self) -> None:
            if not self._authorized():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                data = {}
            try:
                from jobscope.apply import monitoring
                from jobscope.core.store import Store
                with Store(cfg["output"]["db_path"]) as store:
                    result = monitoring.apply_actions(cfg, store, data.get("actions"))
                self._send_json(200, result)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)[:200]})
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self._send_json(500, {"ok": False, "error": str(exc)[:200]})

        # -- routes -------------------------------------------------------
        def do_GET(self):  # noqa: N802 - http.server API
            route = self.path.split("?", 1)[0].split("#", 1)[0]
            if route == "/api/token":
                self._send_json(200, {"token": token, "enabled": refresh_on})
                return
            if route == "/api/status":
                self._send_json(200, dict(_STATE))
                return
            if route in ("/", "/index.html"):
                self._serve_index()
                return
            # SPA client route with no backing file -> serve the (injected) shell.
            fs = self.translate_path(self.path)
            if not os.path.exists(fs) and "." not in os.path.basename(route):
                self._serve_index()
                return
            super().do_GET()

        def do_POST(self):  # noqa: N802 - http.server API
            route = self.path.split("?", 1)[0]
            if route == "/api/outreach":
                self._outreach()
                return
            if route == "/api/company-outreach":
                self._company_outreach()
                return
            if route == "/api/application/update":
                self._application_update()
                return
            if route == "/api/profile/use":
                self._profile_use()
                return
            if route == "/api/resume/upload":
                self._resume_upload()
                return
            if route == "/api/scout":
                self._scout()
                return
            if route == "/api/companies/resolve":
                self._company_resolve()
                return
            if route == "/api/monitoring/actions":
                self._monitoring_actions()
                return
            if route != "/api/refresh":
                self.send_error(404)
                return
            if not refresh_on:
                self._send_json(403, {"state": "error", "message": "refresh disabled"})
                return
            if not self._authorized():
                self._send_json(403, {"state": "error", "message": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            opts: dict = {}
            if length:
                try:
                    opts = json.loads(self.rfile.read(length) or b"{}") or {}
                except ValueError:
                    opts = {}
            force = bool(opts.get("force"))
            full_scan = bool(opts.get("full_scan"))
            with _LOCK:
                if _STATE["state"] == "running":
                    self._send_json(200, {"state": "busy"})
                    return
                _STATE.update(state="running", step="starting", message="Starting\u2026",
                              started=_now(), finished="")
            threading.Thread(target=_run_refresh, args=(cfg, force, full_scan),
                             daemon=True).start()
            self._send_json(200, {"state": "started"})

    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    return Server(("127.0.0.1", port), Handler), "index.html", token, refresh_on


def run(cfg: dict, port: int = 8799, open_browser: bool = False) -> int:
    httpd, page, _token, refresh_on = _build_server(cfg, port)
    port = httpd.server_address[1]
    with httpd:
        url = f"http://127.0.0.1:{port}/{page}"
        print(f"  serving dashboard at {url}  (Ctrl+C to stop)")
        if refresh_on:
            print("  local Gmail scan and profile upload APIs enabled")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped")
    return 0


def perform_refresh(cfg: dict, *, force: bool = False, full_scan: bool = False,
                    on_step=None) -> dict:
    """Run the shared refresh pipeline: (optional scan) -> inbox -> match ->
    publish -> local render.

    Guarded to run at most once per calendar day unless ``force``. Append-only:
    the inbox sync is incremental (UID watermark) and mail events dedupe, so a
    same-day rerun never double-counts. ``on_step(name, message)`` is called
    before each phase. Required stages raise on failure; optional stages are
    reported as degraded. The success marker is written only after publication
    and the local rebuild finish.
    """
    from jobscope.core.store import Store

    def step(name: str, message: str) -> None:
        if on_step:
            on_step(name, message)

    serve_cfg = cfg.get("serve", {}) or {}
    days = int(serve_cfg.get("inbox_days", 7) or 7)
    want_scan = full_scan or bool(serve_cfg.get("refresh_full_scan", False))
    today = _today()
    with Store(cfg["output"]["db_path"]) as store:
        if not force and (store.meta_get("refresh:last_date", "") or "") == today:
            step("skipped", "Already refreshed today.")
            return {"state": "skipped", "message": "Already refreshed today.",
                    "last_date": today, "stages": []}

        stages: list[StageResult] = []
        current_stage = ""
        note = ""
        try:
            from jobscope.ingest import monitor, scrape
            step("monitors", "Scanning monitored company portals")
            stages.append(_run_stage(
                "monitors", required=False,
                action=lambda: monitor.scan_active_monitors(cfg, store),
            ))

            if want_scan or scrape.discovery_due(cfg, store):
                step("scan", "Scanning job boards\u2026")
                stages.append(_run_stage(
                    "scan", required=False,
                    action=lambda: scrape.run(
                        cfg, store, mode="discovery", force_discovery=want_scan,
                    ),
                    nonzero_is_failure=True,
                ))

            step("inbox", f"Syncing Gmail (last {days} days)\u2026")
            from jobscope.ingest import inbox
            since = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
            current_stage = "inbox"
            stages.append(_run_stage(
                "inbox", required=True,
                action=lambda: inbox.run(cfg, store, since=since),
                nonzero_is_failure=True,
            ))

            step("match", "Scoring matches\u2026")
            from jobscope.analyze import match
            current_stage = "match"
            stages.append(_run_stage(
                "match", required=True,
                action=lambda: match.run(cfg, store),
                nonzero_is_failure=True,
            ))

            from jobscope.analyze import review
            stages.append(_run_stage(
                "reviews", required=True,
                action=lambda: review.sync_reviews(store),
            ))

            from jobscope.apply import track as _track
            stages.append(_run_stage(
                "digest", required=False,
                action=lambda: _require_digest(_track.send_digest_result(cfg, store)),
            ))

            # Publish first (it builds the public artifact), then restore web/dist
            # to the local un-redacted dashboard. Both are required for completion.
            step("publish", "Publishing to GitHub Pages\u2026")
            current_stage = "publish"

            def publish() -> None:
                nonlocal note
                note = _publish(cfg)

            stages.append(_run_stage("publish", required=True, action=publish))

            step("render", "Rebuilding local dashboard\u2026")
            current_stage = "render"
            stages.append(_run_stage(
                "render", required=True,
                action=lambda: _build_local_spa(cfg, store),
            ))
        except Exception:
            store.meta_set("refresh:last_failure", _now())
            store.meta_set("refresh:last_failed_stage", current_stage or "unknown")
            store.log_run(f"refresh:{current_stage or 'unknown'}", 0, "error")
            raise

        degraded = any(stage.status == "degraded" for stage in stages)
        store.meta_set("refresh:last_date", today)
        store.meta_set("refresh:last_failure", "")
        store.meta_set("refresh:last_failed_stage", "")
        store.log_run("refresh", 0, "degraded" if degraded else "ok")

    message = ("Refreshed & published with optional-stage warnings."
               if degraded else "Refreshed & published.") + note
    return {"state": "done", "message": message, "last_date": today,
            "degraded": degraded, "stages": [asdict(stage) for stage in stages]}


def _run_refresh(cfg: dict, force: bool, full_scan: bool) -> None:
    """Server background worker: run :func:`perform_refresh`, mirroring progress
    and the outcome into the shared ``_STATE`` for /api/status polling."""
    def on_step(name: str, message: str) -> None:
        _STATE.update(step=name, message=message)

    try:
        res = perform_refresh(cfg, force=force, full_scan=full_scan, on_step=on_step)
        _STATE.update(state=res["state"], step=res["state"], message=res["message"],
                      last_date=res.get("last_date") or _STATE.get("last_date", ""),
                      finished=_now())
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        _STATE.update(state="error", step="error", message=str(exc)[:300],
                      finished=_now())


def _build_local_spa(cfg: dict, store) -> None:
    """Bake un-redacted dashboard data into the web app and run the Vite build,
    producing ``web/dist`` for the LOCAL (localhost-only) view."""
    import shutil

    from . import render

    web = os.path.join(_repo_root(), "web")
    json_path = render.emit_json(cfg, store, public=False)  # -> data/dashboard.json (un-redacted)
    dst = os.path.join(web, "src", "data", "dashboard.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(json_path, dst)
    _npm_build(web)


def _npm_build(web_dir: str) -> None:
    import shutil
    import subprocess

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("npm not found on PATH; install Node.js to build the web dashboard.")
    proc = subprocess.run([npm, "run", "build"], cwd=web_dir, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        raise RuntimeError("web build failed: " + " / ".join(t.strip() for t in tail)[:300])


def _apps_passphrase() -> str:
    """The applications-page passphrase from the environment or OS keychain (or "")."""
    val = os.environ.get("JOBSCOPE_APPS_PASSPHRASE")
    if val:
        return val
    try:
        import keyring
        from jobscope.core.config import KEYRING_SERVICE
        return keyring.get_password(KEYRING_SERVICE, "JOBSCOPE_APPS_PASSPHRASE") or ""
    except Exception:  # noqa: BLE001 - keyring optional / backend may be absent
        return ""


def _has_apps_passphrase() -> bool:
    return bool(_apps_passphrase())


def apps_passphrase_available() -> bool:
    """Return publication-passphrase readiness without exposing its value."""
    return _has_apps_passphrase()


def _publish(cfg: dict) -> str:
    """Build, verify, and push the mandatory encrypted whole-site artifact."""
    import shutil
    import subprocess

    root = _repo_root()
    scripts = os.path.join(root, "scripts")
    have_pass = _has_apps_passphrase()
    if not have_pass:
        raise RuntimeError(
            "JOBSCOPE_APPS_PASSPHRASE is required for whole-site publication")
    env = None

    if os.name == "nt":
        ps1 = os.path.join(scripts, "publish.ps1")
        if not os.path.exists(ps1):
            raise RuntimeError("scripts/publish.ps1 not found.")
        shell = "pwsh" if shutil.which("pwsh") else "powershell"
        args = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1,
                "-Force", "-Encrypted"]
    else:
        sh = os.path.join(scripts, "publish.sh")
        if not os.path.exists(sh):
            raise RuntimeError("scripts/publish.sh not found.")
        args = [shutil.which("bash") or "bash", sh, "--force", "--encrypted"]
        # publish.sh reads the passphrase from the env; hand it the resolved value.
        env = {**os.environ, "JOBSCOPE_APPS_PASSPHRASE": _apps_passphrase()}

    # stdin=DEVNULL so a missing passphrase fails fast instead of blocking on a prompt.
    proc = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL, env=env,
                          capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        raise RuntimeError("publish failed: " + " / ".join(t.strip() for t in tail)[:300])
    return ""
