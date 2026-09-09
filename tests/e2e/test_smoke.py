"""Every page renders and logs no console errors.

The cheapest signal for the most common UI-refactor breakage: a renamed
function, a missing element, a template that throws on load.

Split into public and admin groups: several admin pages fetch admin-only
data (or redirect entirely) for a signed-out visitor, so "no login" is not
a valid way to visit them. See the task report for the anonymous-visitor
findings that split produced.
"""

import pytest

from tests.e2e import seed
from tests.e2e.conftest import console_errors

PUBLIC_PAGES = [
    ("/", "Badminton Tournaments"),
    ("/login.html", "Login"),
]

ADMIN_PAGES = [
    ("/manage.html", "Manage"),
    ("/manage-tournaments.html", "Manage Tournaments"),
    ("/manage-admins.html", "Manage Admins"),
    ("/manage-db.html", "Manage Database - Badminton Admin"),
    ("/manage-komet-players.html", "Manage Komet Players"),
    ("/add-remove-tournaments.html", "Add/Remove Tournaments"),
    ("/email-settings.html", "Email Settings"),
    ("/send-email.html", "Send Email"),
    # Looks public (it's just a results listing), but carries the same
    # client-side is_admin redirect to "/" as the pages above.
    ("/results.html", "Tournament Results"),
]

# No allowlist here on purpose: there is no favicon route, no <link rel=icon>,
# and headless Chromium never requests one, so a "favicon.ico" entry would be
# dead weight -- and test_admin.py already asserts raw errors == [] with no
# allowlist at all. One rule, applied the same way everywhere: any console
# error or uncaught exception fails the test. If a page ever legitimately
# needs to log one, that is the time to add the allowlist back, with a reason
# attached to the specific entry.


def _sign_in_as_admin(page, app_server):
    """Log in through the dev bar's persona picker as the club (admin) account.

    The session lives on the browser context, so this only needs to run
    once per test even if that test then visits several admin pages.

    Same networkidle caveat as test_player.sign_in_as: that state was
    already reached by the page.goto() above, so a same-page fetch() never
    re-arms it. Wait on the login response, then the redirect it triggers.
    """
    page.goto(app_server)
    page.wait_for_selector("#devbar select")
    with page.expect_response(lambda r: "/api/bwf-login" in r.url):
        page.select_option("#devbar select", "sbf04959")
    page.wait_for_url(f"{app_server}/")


def test_console_errors_captures_console_error(app_server, page):
    """Self-check: proves console_errors actually observes what it claims to.

    Task 1 imported this helper without ever calling it. A bug in its event
    filtering would make every smoke test below pass vacuously -- a clean
    page whatever actually happens. This nails down both event types it
    promises to collect before anything else here relies on it.
    """
    with console_errors(page) as errors:
        page.goto(f"{app_server}/login.html")
        # The page's own devbar.js fires a couple of fetches on load. Let them
        # settle before the check below and the context teardown that follows
        # it -- an in-flight request aborted by an abrupt close can wedge the
        # single-threaded dev server for the rest of the run (see every other
        # test in this file waiting on networkidle for the same reason).
        page.wait_for_load_state("networkidle")
        page.evaluate("console.error('harness self-check')")
        page.evaluate(
            "setTimeout(() => { throw new Error('harness pageerror check') }, 0)"
        )
        page.wait_for_timeout(200)
    assert any("harness self-check" in e for e in errors)
    assert any("harness pageerror check" in e for e in errors)


@pytest.mark.parametrize("path,title", PUBLIC_PAGES)
def test_public_page_renders_without_console_errors(app_server, page, path, title):
    with console_errors(page) as errors:
        page.goto(f"{app_server}{path}")
        page.wait_for_load_state("networkidle")
    assert page.title() == title
    assert errors == []


@pytest.mark.parametrize("path,title", ADMIN_PAGES)
def test_admin_page_renders_without_console_errors(app_server, page, path, title):
    _sign_in_as_admin(page, app_server)
    with console_errors(page) as errors:
        page.goto(f"{app_server}{path}")
        page.wait_for_load_state("networkidle")
    assert page.title() == title
    assert errors == []


def test_tournament_page_renders(app_server, page, data_dir):
    """Needs a real tournament in the database to render against."""
    name = seed.open_tournament(data_dir, name="Smoke Cup")
    url = f"https://dev.local/tournament/{name.replace(' ', '-')}"
    with console_errors(page) as errors:
        page.goto(f"{app_server}/tournament.html?url={url}")
        page.wait_for_load_state("networkidle")
    assert page.title() == "Tournament"
    assert errors == []


def test_tournament_detail_page_renders(app_server, page):
    """Title can't be the render check here: the page overwrites
    document.title from a `name` URL param on load, and this URL (matching
    the dev fixture id used elsewhere in this file) doesn't supply one, so
    it always falls back to the literal string "Tournament" instead of the
    static <title>Tournament Detail</title>. #tournament-name is emptied the
    same way (no `name` param -> textContent set to ""), and an empty <h1>
    has no line box in Chromium, so it isn't "visible" either -- check the
    static back-link instead, which the page's JS never touches.
    """
    with console_errors(page) as errors:
        page.goto(f"{app_server}/tournament-detail.html?id=DEV-T1")
        page.wait_for_load_state("networkidle")
    assert page.locator(".back-link").first.is_visible()
    assert errors == []
