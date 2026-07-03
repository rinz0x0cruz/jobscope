"""Document rendering: Markdown -> ATS-safe HTML -> PDF (Playwright/Chromium).

Degrades gracefully: if Playwright or its browser isn't installed, the Markdown
and HTML are still written and the caller is told the PDF was skipped.
"""
from __future__ import annotations

import os
from typing import Any

# Deliberately plain, single-column, standard-font styling so ATS parsers read it cleanly.
_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Calibri','Helvetica Neue',Arial,sans-serif; font-size: 10.6pt;
       color: #111; line-height: 1.35; }
h1 { font-size: 18pt; margin: 0 0 2px; }
h2 { font-size: 12pt; margin: 14px 0 4px; border-bottom: 1px solid #999;
     text-transform: uppercase; letter-spacing: .5px; }
h3 { font-size: 11pt; margin: 8px 0 2px; }
p, li { margin: 2px 0; }
ul { margin: 2px 0 6px 18px; padding: 0; }
a { color: #111; text-decoration: none; }
.contact { color: #333; font-size: 9.6pt; margin-bottom: 4px; }
"""


def markdown_to_html(md_text: str, title: str = "") -> str:
    try:
        import markdown
        body = markdown.markdown(md_text, extensions=["extra", "sane_lists"])
    except ImportError:
        body = "<pre>" + _escape(md_text) + "</pre>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def write_document(md_text: str, out_base: str, title: str = "") -> dict[str, Any]:
    """Write .md + .html (+ .pdf if possible). Returns paths and a `pdf` flag."""
    os.makedirs(os.path.dirname(os.path.abspath(out_base)) or ".", exist_ok=True)
    md_path = out_base + ".md"
    html_path = out_base + ".html"
    pdf_path = out_base + ".pdf"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)
    html = markdown_to_html(md_text, title)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    pdf_ok = render_pdf(html, pdf_path)
    return {"md": md_path, "html": html_path,
            "pdf": pdf_path if pdf_ok else None, "pdf_ok": pdf_ok}


def render_pdf(html: str, out_pdf: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(path=out_pdf, format="A4", print_background=True)
            browser.close()
        return True
    except Exception as e:  # noqa: BLE001 - browser may be missing; fall back to HTML
        print(f"  [pdf] skipped ({e}); HTML written instead. "
              f"Run: python -m playwright install chromium")
        return False


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
