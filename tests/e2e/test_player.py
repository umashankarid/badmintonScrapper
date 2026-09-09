"""The player journey: sign in, register, verify, withdraw."""

from tests.e2e import seed


def sign_in_as(page, base, username):
    """Sign in through the dev bar's persona picker.

    The dropdown's option values are the persona usernames (stable), not the
    display labels -- select_option does not accept a callable predicate.
    """
    page.goto(f"{base}/")
    page.wait_for_selector("#devbar select")
    page.locator("#devbar select").select_option(username)
    page.wait_for_load_state("networkidle")


def tournament_url(name):
    return f"https://dev.local/tournament/{name.replace(' ', '-')}"


def test_player_registers_and_the_row_lands_in_the_database(app_server, page, data_dir):
    name = seed.open_tournament(data_dir, name="Journey Cup")
    sign_in_as(page, app_server, "adam")

    page.goto(f"{app_server}/tournament.html?url={tournament_url(name)}")
    page.wait_for_load_state("networkidle")

    # The level controls are generated into #levels-container at runtime, one
    # row per category, and carry CLASSES not ids (templates/tournament.html:284).
    # #register-section is hidden until login, so waiting on it also proves the
    # sign-in worked.
    page.wait_for_selector("#register-section", state="visible")
    page.locator("select.singles-level").first.select_option("HS A")
    # wait_for_load_state("networkidle") is a no-op here: that state was
    # already reached by the page load above and a same-page fetch() doesn't
    # re-arm it, so the DB check below would race the in-flight POST. Wait on
    # the actual response instead.
    with page.expect_response(lambda r: "/api/add-player" in r.url):
        page.click("#submit-btn")

    rows = seed.registrations_for(data_dir, name)
    assert len(rows) == 1, "registration did not reach the database"
    assert rows[0]["singles_levels"] == "HS A"


def test_player_withdraws_and_the_row_disappears(app_server, page, data_dir):
    name = seed.open_tournament(data_dir, name="Withdraw Cup")
    seed.registration(data_dir, name, "DEV-0001", singles="HS A")
    sign_in_as(page, app_server, "adam")   # DEV-0001 is Adam Adult

    page.goto(f"{app_server}/tournament.html?url={tournament_url(name)}")
    page.wait_for_load_state("networkidle")

    # deletePlayer() confirms upfront (templates/tournament.html:762). Same
    # networkidle caveat as above: wait on the real response, not the state.
    page.once("dialog", lambda d: d.accept())
    with page.expect_response(lambda r: "/api/delete-player" in r.url):
        page.get_by_role("button", name="Withdraw").first.click()

    assert seed.registrations_for(data_dir, name) == []
