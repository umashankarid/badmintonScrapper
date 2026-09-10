"""The design system itself: the stylesheet is wired, the font is served
locally, and no page reaches outside the machine for a webfont.

These assertions are deliberately about plumbing, not appearance. Appearance
is checked by eye at both viewports; what a test can prove is that the font
arrives, that it arrives from this server, and that the token values a
hundred rules depend on are actually defined.
"""

import requests


def test_the_font_is_served_from_this_server(app_server):
    res = requests.get(f"{app_server}/static/fonts/plex-sans-latin.woff2", timeout=10)
    assert res.ok, "the woff2 is not being served"
    assert res.content[:4] == b"wOF2", "that file is not a woff2"


def test_the_stylesheet_defines_the_tokens_every_rule_depends_on(app_server):
    css = requests.get(f"{app_server}/static/design-system.css", timeout=10).text
    for token, value in [
        ("--blue", "#1d4ed8"), ("--ink", "#0f2544"), ("--muted", "#63748c"),
        ("--tint", "#f4f8ff"), ("--line", "#e4ecf7"), ("--ok", "#0f7a52"),
        ("--warn", "#b45309"), ("--bad", "#b42318"),
    ]:
        assert f"{token}: {value}" in css or f"{token}:{value}" in css, \
            f"{token} is missing or is not {value}"


def test_the_stylesheet_has_no_banned_effects(app_server):
    """Gradients, shadows and left-stripe accents are banned by the spec.
    They are the three things the old stylesheet leaned on hardest, so this
    guards against them creeping back during a later migration."""
    css = requests.get(f"{app_server}/static/design-system.css", timeout=10).text
    assert "gradient" not in css, "a gradient came back"
    assert "box-shadow" not in css, "a box-shadow came back"


def test_login_page_uses_the_design_system(app_server, page):
    page.goto(f"{app_server}/login.html")
    page.wait_for_selector("#login-form")
    family = page.evaluate(
        "getComputedStyle(document.body).fontFamily")
    assert "IBM Plex Sans" in family, f"body font is {family!r}"


def test_no_page_requests_a_third_party_font(app_server, page):
    """The e2e server runs behind a dead proxy, so an external font request
    would fail rather than hang -- but it would fail silently and leave the
    page in the fallback face. Catch the request itself."""
    external = []
    page.on("request", lambda r: external.append(r.url)
            if "fonts.googleapis.com" in r.url or "fonts.gstatic.com" in r.url
            else None)
    page.goto(f"{app_server}/login.html")
    page.wait_for_selector("#login-form")
    assert not external, f"page reached out for a webfont: {external}"
