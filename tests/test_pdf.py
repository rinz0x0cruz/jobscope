import sys
import types

from jobscope.deliver import pdf


def test_markdown_html_preserves_formatting_but_neutralizes_raw_html(monkeypatch):
    observed = {}
    module = types.ModuleType("markdown")

    def render(value, extensions):
        observed["input"] = value
        observed["extensions"] = extensions
        return "<h1>Candidate</h1><ul><li>Python</li></ul>" + value

    module.markdown = render
    monkeypatch.setitem(sys.modules, "markdown", module)

    rendered = pdf.markdown_to_html(
        "# Candidate\n\n- Python\n\n"
        "<script>document.body.dataset.leaked = 'yes'</script>\n"
        "<img src='https://attacker.example/pixel' onerror='alert(1)'>",
        "Candidate <script>alert(1)</script>",
    )

    assert "<h1>Candidate</h1>" in rendered
    assert "<li>Python</li>" in rendered
    assert "<script>" not in rendered
    assert "<img src=" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in observed["input"]
    assert observed["extensions"] == ["extra", "sane_lists"]
    assert "default-src 'none'" in rendered
    assert "connect-src 'none'" in rendered


def test_pdf_browser_disables_script_and_network(monkeypatch, tmp_path):
    observed = {}

    class Page:
        def route(self, pattern, handler):
            observed["route"] = pattern
            observed["handler"] = handler

        def set_content(self, html, wait_until):
            observed["html"] = html
            observed["wait_until"] = wait_until

        def pdf(self, **kwargs):
            observed["pdf"] = kwargs

    class Browser:
        def new_page(self, **kwargs):
            observed["page_options"] = kwargs
            return Page()

        def close(self):
            observed["closed"] = True

    class Chromium:
        def launch(self):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class Context:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            return None

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: Context()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)

    assert pdf.render_pdf("<p>Safe</p>", str(tmp_path / "resume.pdf")) is True
    assert observed["page_options"] == {"java_script_enabled": False}
    assert observed["route"] == "**/*"
    assert observed["wait_until"] == "load"
    assert observed["closed"] is True