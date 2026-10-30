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
    assert f"Version {VERSION}" in render_page("index").decode()
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
        for path in ["/", "/files", "/services", "/health", "/data", "/how-it-works", "/privacy", "/faq", "/about"]:
            status, body, resp = web.call("GET", path, token=False)
            assert status == 200 and "text/html" in resp.getheader("Content-Type"), path
        for path, ctype in [("/app.css", "text/css"), ("/files.js", "javascript"), ("/fonts/ah-400.woff2", "font/woff2"), ("/favicon.svg", "image/svg+xml")]:
            status, _, resp = web.call("GET", path, token=False)
            assert status == 200 and ctype in resp.getheader("Content-Type"), path
        status, body, resp = web.call("GET", "/no-such-page", token=False)
        assert status == 404 and b"doesn't exist" in body and "text/html" in resp.getheader("Content-Type")
        assert web.call("GET", "/setup.html", token=False)[0] == 404  # the old addresses are gone
        assert web.call("GET", "/dashboard", token=False)[0] == 404
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


# ---- look and feel ------------------------------------------------------------------
CSS = (STATIC / "app.css").read_text()


def test_no_stroke_down_one_side_of_anything():
    """The design uses whole, subtle borders. A coloured bar down one edge isn't allowed."""
    assert not re.search(r"border-(left|right|inline-start|inline-end)\s*:", CSS)
    assert not re.search(r"border-(left|right)-(color|width|style)", CSS)


def _tokens(block: str) -> dict[str, str]:
    out = {}
    for name, value in re.findall(r"--([a-z-]+):(#[0-9a-fA-F]{3,6})\b", block):
        out[name] = "#" + "".join(c * 2 for c in value[1:]) if len(value) == 4 else value
    return out


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _themes():
    light = _tokens(re.search(r"^:root\{color-scheme:light;(.*?)\}", CSS, re.M).group(1))
    explicit_dark = _tokens(re.search(r"^:root\[data-theme=dark\]\{(.*?)\}", CSS, re.M).group(1))
    system_dark = _tokens(re.search(r"@media \(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{(.*?)\}\}", CSS).group(1))
    return light, explicit_dark, system_dark


def test_dark_mode_works_by_device_setting_and_by_choice_and_they_agree():
    light, explicit_dark, system_dark = _themes()
    assert explicit_dark == system_dark and set(explicit_dark) == set(light)


@pytest.mark.parametrize("which", [0, 1])
def test_text_and_controls_have_enough_contrast_in_both_themes(which):
    t = _themes()[which]
    pairs = [("ink", "paper"), ("ink", "tint"), ("muted", "paper"), ("muted", "tint"), ("blue", "paper"), ("blue", "tint"),
             ("blue-ink", "blue"), ("ok", "paper"), ("ok", "tint"), ("warn", "paper"), ("bad", "paper"), ("bad", "tint")]
    for fg, bg in pairs:
        assert _contrast(t[fg], t[bg]) >= 4.5, f"{fg} on {bg} is {_contrast(t[fg], t[bg]):.1f}:1"


@pytest.mark.parametrize("slug", [s for s in SLUGS])
def test_every_page_has_the_theme_switch_and_applies_it_before_painting(slug):
    html = render_page(slug).decode()
    assert html.index('src="/theme.js"') < html.index('href="/app.css"'), "the theme must be set before styles load"
    for choice in ("system", "light", "dark"):
        assert f'data-theme-set="{choice}"' in html


def test_the_front_page_is_wide_and_other_pages_are_not():
    assert 'class="main-col w-wide"' in render_page("index").decode()
    assert 'class="main-col w-narrow"' in render_page("faq").decode()
    assert 'class="main-col w-wide"' in render_page("files").decode()  # the Files page uses the whole width


@pytest.mark.parametrize("slug", [s for s in SLUGS])
def test_every_page_has_a_sidebar_with_icons_and_no_collapse_toggle(slug):
    html = render_page(slug).decode()
    assert 'id="collapse"' not in html and "Collapse sidebar" not in html  # a desktop-style app has a fixed sidebar
    assert html.count('<use href="#i-') >= 9  # one icon per link, drawn from the inline sprite (nothing loads from outside)
    assert 'src="http' not in html and "style=" not in html
    # every icon-only control still has a name for screen readers
    assert '<span class="sr">Dark</span>' in html


def test_the_files_page_can_select_files_and_remove_all():
    html = render_page("files").decode()
    for hook in ('id="all"', 'id="picked"', 'id="rm"', 'id="removeall"'):
        assert hook in html
    js = (STATIC / "files.js").read_text()
    assert "files: names" in js  # a run names the ticked files


ACCENTS = ["teal", "green", "purple", "rose", "amber"]


@pytest.mark.parametrize("accent", ACCENTS)
def test_every_accent_color_is_readable_as_text_and_under_button_ink(accent):
    light, dark, _ = _themes()
    light_accent = _tokens(re.search(rf"^:root\[data-accent={accent}\]\{{(.*?)\}}", CSS, re.M).group(1))["blue"]
    dark_accent = _tokens(re.search(rf"^:root\[data-theme=dark\]\[data-accent={accent}\]\{{(.*?)\}}", CSS, re.M).group(1))["blue"]
    system_dark = _tokens(re.search(rf"\(prefers-color-scheme:dark\)\{{:root:not\(\[data-theme=light\]\)\[data-accent={accent}\]\{{(.*?)\}}", CSS).group(1))["blue"]
    assert dark_accent == system_dark
    for t, color in ((light, light_accent), (dark, dark_accent)):
        for bg in ("paper", "tint"):
            assert _contrast(color, t[bg]) >= 4.5, f"{accent} on {bg}"
        assert _contrast(t["blue-ink"], color) >= 4.5, f"button text on {accent}"


def test_the_accent_choice_is_offered_everywhere_and_applied_before_painting():
    html = render_page("files").decode()
    for name in ["blue"] + ACCENTS:
        assert f'data-accent-set="{name}"' in html
    assert "cappv1.accent" in (STATIC / "theme.js").read_text()


def test_the_app_fills_the_window_and_scrolls_inside():
    assert re.search(r"\.shell\{[^}]*height:100vh", CSS) and re.search(r"\.main-col\{[^}]*overflow:auto", CSS)


def test_the_app_can_be_installed():
    html = render_page("files").decode()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    import json

    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone" and manifest["start_url"].startswith("/")
    for icon in manifest["icons"]:
        assert (STATIC / icon["src"].lstrip("/")).is_file()


def test_cards_show_only_a_question_mark_for_processing_notes():
    js = (STATIC / "files.js").read_text()
    assert 'role: "tooltip"' in js and '"?"' in js and "skipNotes" not in js
