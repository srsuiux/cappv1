import re
from pathlib import Path

import pytest

from src.web.server import STATIC
from tests.test_web_api import Client, WebServer

PAGES = sorted(STATIC.glob("*.html"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_obey_the_content_policy(page):
    """The server's policy forbids inline script and style, so a page that uses
    either would silently break in the browser."""
    html = page.read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline script"
    assert not re.search(r"<style", html), "inline style block"
    assert not re.search(r"\sstyle=", html), "inline style attribute"
    assert not re.search(r"\son[a-z]+=", html), "inline event handler"
    assert 'lang="en"' in html and "<title>" in html and 'href="#main"' in html


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_everything_a_page_loads_exists(page):
    html = page.read_text()
    refs = re.findall(r'(?:src|href)="([^"#:]+)"', html)
    assert refs
    for ref in refs:
        assert (STATIC / ref).is_file(), f"{page.name} refers to missing {ref}"


def test_scripts_import_only_local_files():
    for js in STATIC.glob("*.js"):
        for ref in re.findall(r'from "(\./[^"]+)"', js.read_text()):
            assert (STATIC / ref).is_file()
        assert not re.search(r"https?://", js.read_text()), f"{js.name} reaches outside"


def test_assets_are_served_with_the_right_types(configured):
    server = WebServer(configured, port=0)
    server.start()
    try:
        web = Client(server)
        for path, ctype in [("/", "text/html"), ("/setup.html", "text/html"), ("/app.css", "text/css"),
                            ("/home.js", "javascript"), ("/fonts/ah-400.woff2", "font/woff2")]:
            status, _, resp = web.call("GET", path, token=False)
            assert status == 200 and ctype in resp.getheader("Content-Type"), path
    finally:
        server.stop()
