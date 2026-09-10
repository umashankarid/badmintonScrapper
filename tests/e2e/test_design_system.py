"""The design system itself: the stylesheet is wired, the font is served
locally, and no page reaches outside the machine for a webfont.

These assertions are deliberately about plumbing, not appearance. Appearance
is checked by eye at both viewports; what a test can prove is that the font
arrives, that it arrives from this server, and that the token values a
hundred rules depend on are actually defined.
"""

import requests

from tests.e2e import seed
from tests.e2e.test_player import sign_in_as


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


def test_tournament_card_is_stacked_on_a_phone_and_sideways_on_a_desktop(
        app_server, page, data_dir):
    """The one layout decision on this page: the card turns sideways at
    768px rather than the list becoming a grid. Assert the flex direction
    rather than pixel positions -- positions move every time copy changes,
    the direction is the actual decision."""
    # groups=["SENIOR"] matches Adam's persona (bwf_dev.py) -- open_tournaments()
    # (app.py) hides a group-less fixture from any signed-in player who has
    # groups, so a plain open_tournament() call here would time out on
    # `.t-card__main` for reasons that have nothing to do with this page's
    # markup.
    seed.open_tournament(data_dir, name="Breakpoint Cup", groups=["SENIOR"])
    sign_in_as(page, app_server, "adam")

    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{app_server}/")
    page.wait_for_selector(".t-card__main")
    assert page.evaluate(
        "getComputedStyle(document.querySelector('.t-card__main')).flexDirection"
    ) == "column"

    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_function(
        "getComputedStyle(document.querySelector('.t-card__main')).flexDirection === 'row'"
    )


def test_registration_form_stays_one_column_at_every_width(
        app_server, page, data_dir):
    """Width buys context, not parallel inputs. If the form ever becomes two
    columns, the singles and doubles pickers end up side by side -- which is
    precisely how someone registers for the wrong event.

    Passes before the Task 8 migration as well as after: the old form was
    already one column. It is a regression guard for the two-pane layout, not
    a red-to-green cycle.
    """
    name = seed.open_tournament(data_dir, name="One Column Cup", groups=["SENIOR"])
    sign_in_as(page, app_server, "adam")

    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{app_server}/tournament.html?url={seed.tournament_url(name)}")
    page.wait_for_selector("#register-section", state="visible")

    singles = page.locator("select.singles-level").first.bounding_box()
    doubles = page.locator("select.doubles-level").first.bounding_box()
    assert doubles["y"] >= singles["y"] + singles["height"], \
        "the level pickers are side by side; the form went two-column"
