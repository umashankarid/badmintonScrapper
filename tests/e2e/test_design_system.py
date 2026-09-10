"""The design system itself: the stylesheet is wired, the font is served
locally, and no page reaches outside the machine for a webfont.

These assertions are deliberately about plumbing, not appearance. Appearance
is checked by eye at both viewports; what a test can prove is that the font
arrives, that it arrives from this server, and that the token values a
hundred rules depend on are actually defined.
"""

import re
from pathlib import Path

import requests

from tests.e2e import seed
from tests.e2e.test_player import sign_in_as

REPO_ROOT = Path(__file__).resolve().parents[2]


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


BANNED_EFFECTS = [
    ("a gradient", re.compile(r"gradient\s*\(")),
    ("a shadow", re.compile(r"(?:box|text|drop)-shadow\s*[:(]")),
    ("a border accent stripe", re.compile(r"border-(?:left|right)(?:-(?:width|color|style))?\s*:")),
]


def test_no_stylesheet_or_template_has_a_banned_effect():
    """Gradients, shadows and left-stripe accents are banned by the spec.
    They are the three things the old design leaned on hardest.

    Two things this used to miss and no longer does. It named left-stripe
    accents in its own docstring and never checked for one -- the pattern
    this redesign removed the most of. And it read only the stylesheet, so
    any of the surviving inline style= attributes could have carried a
    gradient past it. Matching on the declaration (a colon or an opening
    paren after the property) rather than the bare word is what lets the
    prose in these comments say "box-shadow" without tripping the guard.
    """
    targets = [REPO_ROOT / "static" / "design-system.css"]
    targets += sorted((REPO_ROOT / "templates").glob("*.html"))
    offenders = {}
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for label, pattern in BANNED_EFFECTS:
            if pattern.search(text):
                offenders.setdefault(path.name, []).append(label)
    assert not offenders, f"banned effects came back: {offenders}"


def test_login_page_uses_the_design_system(app_server, page):
    page.goto(f"{app_server}/login.html")
    page.wait_for_selector("#login-form")
    family = page.evaluate(
        "getComputedStyle(document.body).fontFamily")
    assert "IBM Plex Sans" in family, f"body font is {family!r}"


def test_the_login_page_requests_no_third_party_font(app_server, page):
    """The e2e server runs behind a dead proxy, so an external font request
    would fail rather than hang -- but it would fail silently and leave the
    page in the fallback face. Catch the request itself.

    Renamed: this was called test_no_page_requests_a_third_party_font and
    visited exactly one page. It is the runtime half of the pair; the
    static scan below is the half that actually covers every page.
    """
    external = []
    page.on("request", lambda r: external.append(r.url)
            if "fonts.googleapis.com" in r.url or "fonts.gstatic.com" in r.url
            else None)
    page.goto(f"{app_server}/login.html")
    page.wait_for_selector("#login-form")
    assert not external, f"page reached out for a webfont: {external}"


def test_no_template_links_a_third_party_font():
    """Every page, not just the one the browser test happens to visit."""
    offenders = [
        p.name for p in (REPO_ROOT / "templates").glob("*.html")
        if "fonts.googleapis.com" in p.read_text(encoding="utf-8")
        or "fonts.gstatic.com" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"templates link an external webfont: {offenders}"


def test_every_template_links_the_design_system():
    """Nothing else covers this. A template that links no stylesheet at all
    renders as unstyled markup and every other assertion here still passes --
    the token test reads the CSS directly, the font test visits one page, and
    the smoke tests only check the title and the console."""
    offenders = [
        p.name for p in (REPO_ROOT / "templates").glob("*.html")
        if "/static/design-system.css" not in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"templates not linking the design system: {offenders}"


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


def test_no_template_references_the_old_stylesheet():
    """styles.css is deleted. A template still linking it renders unstyled,
    and nothing else in the suite would notice."""
    offenders = [
        p.name for p in (REPO_ROOT / "templates").glob("*.html")
        if "styles.css" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"still linking the deleted stylesheet: {offenders}"


def test_the_old_stylesheet_is_gone():
    assert not (REPO_ROOT / "static" / "styles.css").exists()


def test_no_template_uses_emoji_as_an_icon():
    """The old templates leaned on emoji for status and category icons. Every
    one carried meaning that a screen reader announces as a picture name, or
    no meaning at all. The redesign replaces the meaningful ones with words
    and deletes the decorative ones. These ranges are pictographs and
    dingbats only -- accented Latin (aa, ae, oe) is nowhere near them."""
    import re
    pattern = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF]")
    offenders = {}
    for path in (REPO_ROOT / "templates").glob("*.html"):
        found = pattern.findall(path.read_text(encoding="utf-8"))
        if found:
            offenders[path.name] = sorted(set(found))
    assert not offenders, f"emoji used as icons: {offenders}"


def test_templates_carry_almost_no_inline_styles():
    """Inline style= attributes are how the old design drifted, so this is a
    ratchet: the count may fall, it must never rise. If a future change
    legitimately needs one more, raise the number in the same commit and say
    why in the commit message -- do not delete a legitimate survivor just to
    keep the number down.

    It does NOT sort into three clean categories, and this docstring used to
    claim it did. Measured honestly, across templates/*.html the day
    styles.css was deleted: roughly 96 are spacing and flex/gap wrappers
    reaching for var(--sp-*) tokens or meeting the >=8px tap-target floor,
    roughly 51 are display toggles the scripts flip directly, and the
    remaining ~76 are ordinary typography and interaction styling that
    hasn't been componentized yet -- bare font-weight, text-align:center,
    cursor:pointer, a couple of JS-computed dynamic values (the "Submit to
    BWF" progress bar's animated width, and its fill colour, which
    intentionally differs between tournament.html and
    manage-tournaments.html), and the two modals' per-instance backdrop
    opacity/z-index. The modal backdrop and progress-bar/track structure
    used to be pasted twice each (manage-db.html + manage-tournaments.html;
    tournament.html + manage-tournaments.html) and now live once each as
    .modal-overlay / .progress-track / .progress-bar in
    static/design-system.css -- fix round 1 folded those two duplicate
    pairs in, which is why the budget dropped from 225 to 223. The final
    review round then took it to 222: two more went (the BWF picker row's
    max-width wrapper became .pick-row__controls, and manage-db's per-cell
    word-break became .table--clip) against one added (manage-admins.html's
    topbar name, copied verbatim from the other admin pages).
    """
    from collections import Counter
    counts = Counter()
    for p in (REPO_ROOT / "templates").glob("*.html"):
        n = p.read_text(encoding="utf-8").count('style="')
        if n:
            counts[p.name] = n
    total = sum(counts.values())
    assert total <= 222, (
        f"{total} inline style= attributes across templates, budget is 222: "
        f"{dict(counts.most_common())}. Put appearance in "
        "static/design-system.css.")
