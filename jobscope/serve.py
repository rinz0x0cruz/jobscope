"""Serve the dashboard directory over local HTTP (mirrors exploitrank `serve`)."""
from __future__ import annotations

import functools
import http.server
import os
import socketserver
import webbrowser


def run(cfg: dict, port: int = 8799, open_browser: bool = False) -> int:
    from . import render
    from .store import Store

    with Store(cfg["output"]["db_path"]) as store:
        path = render.build(cfg, store)

    directory = os.path.dirname(os.path.abspath(path)) or "."
    page = os.path.basename(path)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    class Quiet(socketserver.TCPServer):
        allow_reuse_address = True

    with Quiet(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/{page}"
        print(f"  serving {directory} at {url}  (Ctrl+C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped")
    return 0
