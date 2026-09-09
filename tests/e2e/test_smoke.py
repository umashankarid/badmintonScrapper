"""Every page renders, with no console errors."""

from tests.e2e.conftest import console_errors


def test_harness_boots_in_dev_mode(app_server, page):
    """Proves the fixture works before any real test depends on it."""
    page.goto(f"{app_server}/login.html")
    assert page.title() == "Login"
    # The bar only renders when DEV_TOOLS is set and the mode is dev.
    assert page.locator("#devbar").is_visible()
