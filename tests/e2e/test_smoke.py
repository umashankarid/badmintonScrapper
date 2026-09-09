"""Every page renders and logs no console errors.

The cheapest signal for the most common UI-refactor breakage: a renamed
function, a missing element, a template that throws on load.
"""

import pytest

from tests.e2e import seed
from tests.e2e.conftest import console_errors

PAGES = [
    ("/", "Badminton Tournaments"),
    ("/login.html", "Login"),
    ("/results.html", "Tournament Results"),
    ("/manage.html", "Manage"),
    ("/manage-tournaments.html", "Manage Tournaments"),
    ("/manage-admins.html", "Manage Admins"),
    ("/manage-db.html", "Manage Database - Badminton Admin"),
    ("/manage-komet-players.html", "Manage Komet Players"),
    ("/add-remove-tournaments.html", "Add/Remove Tournaments"),
    ("/email-settings.html", "Email Settings"),
    ("/send-email.html", "Send Email"),
    ("/tournament-detail.html?id=DEV-T1", "Tournament Detail"),
]

# Errors a page legitimately produces. Every entry needs a reason; an
# allowlist that grows without them is how this assertion stops meaning
# anything.
ALLOWED = (
    "favicon.ico",   # no favicon is shipped; the browser always requests one
)


def _unexpected(errors):
    return [e for e in errors if not any(a in e for a in ALLOWED)]


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


@pytest.mark.parametrize("path,title", PAGES)
def test_page_renders_without_console_errors(app_server, page, path, title):
    with console_errors(page) as errors:
        page.goto(f"{app_server}{path}")
        page.wait_for_load_state("networkidle")
    assert page.title() == title
    assert _unexpected(errors) == []


def test_tournament_page_renders(app_server, page, data_dir):
    """Needs a real tournament in the database to render against."""
    name = seed.open_tournament(data_dir, name="Smoke Cup")
    url = f"https://dev.local/tournament/{name.replace(' ', '-')}"
    with console_errors(page) as errors:
        page.goto(f"{app_server}/tournament.html?url={url}")
        page.wait_for_load_state("networkidle")
    assert page.title() == "Tournament"
    assert _unexpected(errors) == []
