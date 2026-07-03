"""Offline enrichment tests -- all network calls are monkeypatched."""
from jobscope.enrich import comp, contacts, news, reddit, stock
from jobscope.model import Job


# ---- comp (pure) --------------------------------------------------------
def test_comp_formats_range_and_links():
    job = Job(company="Acme Inc", salary_min=120000, salary_max=150000,
              currency="USD", salary_interval="yearly")
    out = comp.enrich("Acme Inc", job)
    assert out["range"] == "$120k–$150k/yearly"
    assert "levels.fyi" in out["levels_fyi"]


def test_comp_without_salary_still_gives_links():
    out = comp.enrich("Acme", Job(company="Acme"))
    assert "range" not in out
    assert out["levels_search"].startswith("https://www.levels.fyi")


# ---- reddit sentiment lexicon ------------------------------------------
def test_reddit_label():
    assert reddit._label(4, 0) == "positive"
    assert reddit._label(0, 4) == "negative"
    assert reddit._label(3, 2) == "mixed"
    assert reddit._label(0, 0) == "neutral"


def test_reddit_parses_and_scores(monkeypatch):
    payload = {"data": {"children": [
        {"data": {"title": "Great WLB and supportive team at Acme", "subreddit": "cscareerquestions",
                  "score": 42, "num_comments": 10, "permalink": "/r/x/1"}},
        {"data": {"title": "Acme layoffs and toxic burnout", "subreddit": "jobs",
                  "score": 5, "num_comments": 2, "permalink": "/r/x/2"}},
    ]}}
    monkeypatch.setattr(reddit.httpx, "get_json", lambda *a, **k: payload)
    out = reddit.enrich("Acme")
    assert out["count"] == 2
    assert out["sentiment"] in ("positive", "mixed", "negative")
    assert out["posts"][0]["score"] == 42  # sorted by score


# ---- stock resolution ---------------------------------------------------
def test_stock_private_when_no_equity(monkeypatch):
    monkeypatch.setattr(stock.httpx, "get_json", lambda *a, **k: {"quotes": []})
    out = stock.enrich("Some Private Startup")
    assert out["public"] is False


def test_stock_helpers():
    assert stock._human(2.77e12) == "$2.8T"
    assert stock._human(4.8e9) == "$4.8B"
    assert stock._norm("Acme, Inc.") == "acme"
    assert stock._match_score("acme", "acme", {"exchange": "NMS"}) >= 100


def test_stock_known_private_override(monkeypatch):
    # a curated-private company never shows a public listing, even if Yahoo returns one
    monkeypatch.setattr(stock.httpx, "get_json", lambda *a, **k: {
        "quotes": [{"quoteType": "EQUITY", "symbol": "038620.KQ",
                    "shortname": "WIZ Corp", "exchange": "KSC"}]})
    assert stock._resolve_ticker("wiz") == (None, None)
    assert stock.enrich("wiz")["public"] is False


def test_stock_rejects_foreign_listing(monkeypatch):
    # an unmapped company must not be matched to an overseas ".KQ" listing
    monkeypatch.setattr(stock.httpx, "get_json", lambda *a, **k: {
        "quotes": [{"quoteType": "EQUITY", "symbol": "1234.KQ",
                    "shortname": "Acme", "exchange": "KSC"}]})
    assert stock._resolve_ticker("Acme Unlisted Co") == (None, None)


def test_stock_accepts_us_primary_listing(monkeypatch):
    monkeypatch.setattr(stock.httpx, "get_json", lambda *a, **k: {
        "quotes": [{"quoteType": "EQUITY", "symbol": "ACME",
                    "shortname": "Acme, Inc.", "exchange": "NMS"}]})
    assert stock._resolve_ticker("Acme") == ("ACME", "Acme, Inc.")


def test_stock_known_public_override(monkeypatch):
    # curated public map resolves deterministically without any network call
    def _boom(*a, **k):
        raise AssertionError("Yahoo search should not be called for a mapped company")
    monkeypatch.setattr(stock.httpx, "get_json", _boom)
    assert stock._resolve_ticker("Datadog") == ("DDOG", None)


# ---- contacts (legit-only) ---------------------------------------------
def test_contacts_returns_search_leads_without_github(monkeypatch):
    monkeypatch.setattr(contacts.httpx, "get_json", lambda *a, **k: None)
    leads = contacts.find("Acme", Job(company="Acme", title="Security Engineer"))
    sources = {c.source for c in leads}
    assert "linkedin-search" in sources and "google-search" in sources
    for c in leads:
        assert c.search_url and "Acme".lower() in c.search_url.lower()
    # ids are stable across runs
    again = contacts.find("Acme", Job(company="Acme", title="Security Engineer"))
    assert {c.id for c in leads} == {c.id for c in again}


def test_contacts_includes_public_github_profiles(monkeypatch):
    def fake_get_json(url, **kwargs):
        if "search/users" in url:
            return {"items": [{"login": "octo", "html_url": "https://github.com/octo"}]}
        return {"login": "octo", "name": "Octo Cat", "company": "Acme",
                "bio": "Security engineer at Acme", "html_url": "https://github.com/octo"}
    monkeypatch.setattr(contacts.httpx, "get_json", fake_get_json)
    leads = contacts.find("Acme", Job(company="Acme", title="Security Engineer"))
    gh = [c for c in leads if c.source == "github"]
    assert gh and gh[0].name == "Octo Cat"
    assert gh[0].outreach and "Octo" in gh[0].outreach


# ---- news dedup ---------------------------------------------------------
def test_news_dedup(monkeypatch):
    class E:
        def __init__(self, title, link):
            self.title, self.link, self.published = title, link, ""
    class Feed:
        entries = [E("Acme raises Series C", "l1"), E("Acme raises Series C", "l1"),
                   E("Acme hires CISO", "l2")]
    import types
    fake = types.SimpleNamespace(parse=lambda url: Feed())
    monkeypatch.setitem(__import__("sys").modules, "feedparser", fake)
    out = news.enrich("Acme", [])
    titles = [i["title"] for i in out]
    assert titles.count("Acme raises Series C") == 1
    assert len(out) == 2
