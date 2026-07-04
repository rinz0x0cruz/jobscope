"""Serve the dashboard over local HTTP, with an optional localhost-only
"Refresh & Publish" endpoint.

`jobscope serve` builds the static dashboard and serves it on 127.0.0.1. When
`serve.refresh_enabled` is set (the default), the served page shows a Refresh &
Publish button that POSTs to ``/api/refresh``; the server then syncs the Gmail
inbox (last ``serve.inbox_days`` days, append-only), rescores matches, rebuilds
the dashboard, and publishes the redacted/encrypted site -- at most once per day
unless forced. The endpoints bind to loopback and are CSRF-guarded (localhost
Origin + a per-run token); they never exist on the published static site.
"""
from __future__ import annotations

import datetime as _dt
import http.server
import json
import os
import secrets
import threading
import webbrowser

# Single-process refresh state, shared between the request threads and the
# background worker. Writes are small dict.update() calls (atomic under the GIL);
# _LOCK only guards the "is one already running?" decision in do_POST.
_LOCK = threading.Lock()
_STATE: dict[str, str] = {
    "state": "idle",     # idle | running | done | skipped | error | busy
    "step": "",          # scan | inbox | match | render | publish | ...
    "message": "",
    "started": "",
    "finished": "",
    "last_date": "",     # YYYY-MM-DD of the last successful refresh
}


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return _dt.date.today().isoformat()


def _repo_root() -> str:
    # .../<root>/jobscope/deliver/serve.py -> <root>
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_server(cfg: dict, port: int):
    """Build (but do not start) the dashboard HTTP server with the refresh API
    wired in. Returns ``(httpd, page, token, refresh_enabled)``. Exposed so tests
    can drive the endpoints on an ephemeral port."""
    from . import render
    from jobscope.core.store import Store

    with Store(cfg["output"]["db_path"]) as store:
        path = render.build(cfg, store)
        _STATE["last_date"] = store.meta_get("refresh:last_date", "") or ""

    directory = os.path.dirname(os.path.abspath(path)) or "."
    page = os.path.basename(path)
    serve_cfg = cfg.get("serve", {}) or {}
    refresh_on = bool(serve_cfg.get("refresh_enabled", True))
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

        # -- routes -------------------------------------------------------
        def do_GET(self):  # noqa: N802 - http.server API
            route = self.path.split("?", 1)[0]
            if route == "/api/token":
                self._send_json(200, {"token": token, "enabled": refresh_on})
                return
            if route == "/api/status":
                self._send_json(200, dict(_STATE))
                return
            super().do_GET()

        def do_POST(self):  # noqa: N802 - http.server API
            route = self.path.split("?", 1)[0]
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

    return Server(("127.0.0.1", port), Handler), page, token, refresh_on


def run(cfg: dict, port: int = 8799, open_browser: bool = False) -> int:
    httpd, page, _token, refresh_on = _build_server(cfg, port)
    port = httpd.server_address[1]
    with httpd:
        url = f"http://127.0.0.1:{port}/{page}"
        print(f"  serving dashboard at {url}  (Ctrl+C to stop)")
        if refresh_on:
            print("  refresh & publish button enabled (localhost only)")
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
    render -> publish.

    Guarded to run at most once per calendar day unless ``force``. Append-only:
    the inbox sync is incremental (UID watermark) and mail events dedupe, so a
    same-day rerun never double-counts. ``on_step(name, message)`` is called
    before each phase. Raises on failure; returns a dict with ``state`` (``done``
    or ``skipped``), ``message`` and ``last_date``. Used by both the serve button
    and the ``refresh`` CLI command / scheduled task.
    """
    from . import render
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
                    "last_date": today}
        if want_scan:
            step("scan", "Scanning job boards\u2026")
            from jobscope.ingest import scrape
            scrape.run(cfg, store)
        step("inbox", f"Syncing Gmail (last {days} days)\u2026")
        from jobscope.ingest import inbox
        since = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        inbox.run(cfg, store, since=since)
        step("match", "Scoring matches\u2026")
        from jobscope.analyze import match
        match.run(cfg, store)
        step("render", "Rebuilding dashboard\u2026")
        render.build(cfg, store)
        store.meta_set("refresh:last_date", today)
        store.log_run("refresh", 0, "ok")
    step("publish", "Publishing to GitHub Pages\u2026")
    note = _publish(cfg)
    return {"state": "done", "message": "Refreshed & published." + note,
            "last_date": today}


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


def _has_apps_passphrase() -> bool:
    if os.environ.get("JOBSCOPE_APPS_PASSPHRASE"):
        return True
    try:
        import keyring
        from jobscope.core.config import KEYRING_SERVICE
        return bool(keyring.get_password(KEYRING_SERVICE, "JOBSCOPE_APPS_PASSPHRASE"))
    except Exception:  # noqa: BLE001 - keyring optional / backend may be absent
        return False


def _publish(cfg: dict) -> str:
    """Run scripts/publish.ps1 to build + push the redacted (and, when a
    passphrase is available, encrypted) site. Returns a short status note."""
    import shutil
    import subprocess

    root = _repo_root()
    ps1 = os.path.join(root, "scripts", "publish.ps1")
    if os.name != "nt" or not os.path.exists(ps1):
        raise RuntimeError("Publishing is Windows-only for now (scripts/publish.ps1).")
    shell = "pwsh" if shutil.which("pwsh") else "powershell"
    args = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, "-Force"]
    note = ""
    if _has_apps_passphrase():
        args.append("-Encrypted")
    else:
        note = " (applications page skipped \u2014 set JOBSCOPE_APPS_PASSPHRASE in the keychain)"
    # stdin=DEVNULL so a missing passphrase fails fast instead of blocking on a prompt.
    proc = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        raise RuntimeError("publish.ps1 failed: " + " / ".join(t.strip() for t in tail)[:300])
    return note
