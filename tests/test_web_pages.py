import re

import pytest

from src.version import VERSION
from src.web.server import PAGES, STATIC, WebServer, render_page
from tests.test_web_api import Client

SLUGS = sorted(p.stem for p in PAGES.glob("*.html"))
INTERNAL = re.compile(r'(?:href|src)="(/[^"#]*)"')


def page_exists(path: str) -> bool:
    slug = path.strip("/") or "index"
    return (PAGES / f"{slug}.html").is_file() or (STATIC / path.lstrip("/")).is_file()


@pytest.mark.parametrize("slug", SLUGS)
def test_pages_obey_the_content_policy(slug):
    """The server's policy forbids inline script and style, so a page that uses
    either would silently break in the browser."""
    html = render_page(slug).decode()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline script"
    assert "<style" not in html and not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)
    assert 'lang="en"' in html and "<title>" in html and 'href="#main"' in html and '<main id="main">' in html
    assert html.count("<h1") == 1, "one h1 per page"
    assert "{{" not in html, "an unfilled placeholder"
    assert "<!--" not in html.split("<body")[1], "page metadata leaked into the output"


@pytest.mark.parametrize("slug", SLUGS)
def test_every_internal_link_and_asset_exists(slug):
    for ref in INTERNAL.findall(render_page(slug).decode()):
        assert page_exists(ref), f"{slug} points at missing {ref}"


@pytest.mark.parametrize("slug", SLUGS)
def test_external_links_open_safely(slug):
    for tag in re.findall(r"<a [^>]*>", render_page(slug).decode()):
        if 'target="_blank"' in tag:
            assert "noopener" in tag and "noreferrer" in tag


def test_the_current_page_is_marked_in_the_menu():
    html = render_page("privacy").decode()
    assert re.search(r'data-nav="privacy" aria-current="page"', html)
    assert html.count('aria-current="page"') == 1


def test_footer_and_about_show_the_version():
    assert f"Version {VERSION}" in render_page("dashboard").decode()
    assert f"This is cappv1 {VERSION}." in render_page("about").decode()


def test_scripts_import_only_local_files():
    for js in STATIC.glob("*.js"):
        text = js.read_text()
        for ref in re.findall(r'from "(/[^"]+)"', text) + re.findall(r'^import "(/[^"]+)"', text, re.M):
            assert (STATIC / ref.lstrip("/")).is_file(), f"{js.name} imports missing {ref}"
        assert not re.search(r"https?://", text), f"{js.name} reaches outside"


def test_each_page_script_exists():
    for slug in SLUGS:
        for src in re.findall(r'<script type="module" src="(/[^"]+)"', render_page(slug).decode()):
            assert (STATIC / src.lstrip("/")).is_file(), f"{slug}: {src}"


def test_pages_and_assets_are_served(configured):
    server = WebServer(configured, port=0)
    server.start()
    try:
        web = Client(server)
        for path in ["/", "/dashboard", "/files", "/services", "/health", "/data", "/how-it-works", "/privacy", "/faq", "/about"]:
            status, body, resp = web.call("GET", path, token=False)
            assert status == 200 and "text/html" in resp.getheader("Content-Type"), path
        for path, ctype in [("/app.css", "text/css"), ("/files.js", "javascript"), ("/fonts/ah-400.woff2", "font/woff2")]:
            status, _, resp = web.call("GET", path, token=False)
            assert status == 200 and ctype in resp.getheader("Content-Type"), path
        status, body, resp = web.call("GET", "/no-such-page", token=False)
        assert status == 404 and b"doesn't exist" in body and "text/html" in resp.getheader("Content-Type")
        assert web.call("GET", "/setup.html", token=False)[0] == 404  # the old address is gone
    finally:
        server.stop()


def test_privacy_page_states_what_the_code_actually_sends():
    """If these facts change in the code, this page must change with it."""
    from src import llm_client
    text = render_page("privacy").decode()
    for claim in ("speaker notes", "127.0.0.1", "Ollama", "OpenRouter", "OpenAI", "Anthropic", ".state/", "logs/", ".env"):
        assert claim in text
    # the request builder sends these parts of the slide context; the page lists them
    from src.pptx_reader import SlideContext
    ctx = SlideContext(0, "Sec", "Title", "Body", "Notes")
    sent = llm_client._context_text(ctx)
    for part in ("Title", "Sec", "Body", "Notes"):
        assert part in sent
