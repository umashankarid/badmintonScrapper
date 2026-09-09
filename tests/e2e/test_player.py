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


def test_under_13_sees_the_dispens_confirmation(app_server, page, data_dir):
    """Mini Minior is 11. Senior classes require a confirmation popup."""
    name = seed.open_tournament(data_dir, name="Dispens Cup")
    sign_in_as(page, app_server, "mini")
    page.goto(f"{app_server}/tournament.html?url={tournament_url(name)}")
    page.wait_for_load_state("networkidle")

    seen = []
    page.on("dialog", lambda d: (seen.append(d.message), d.dismiss()))
    page.wait_for_selector("#register-section", state="visible")
    page.locator("select.singles-level").first.select_option("DS B")
    # The confirm() only appears after /api/add-player's (validation) response
    # comes back and the JS decides to ask permission. networkidle/timeout
    # would race that fetch, same caveat as the happy-path tests above --
    # wait on the dialog itself instead: it's the exact event this assertion
    # needs, and it is strictly downstream of the response.
    with page.expect_event("dialog"):
        page.click("#submit-btn")

    assert seen, "no confirmation appeared for an under-13 in a senior class"
    assert seed.registrations_for(data_dir, name) == [], "dismissed but still registered"


def test_level_3_5_player_is_blocked_from_an_sjt_event(app_server, page, data_dir):
    """Jonas is LEVEL 3-5: MJT only. The block is server-side; the UI must show it.

    Deliberately does not use seed.sjt_tournament()'s categories: "HS U15" is
    also rejected by the unrelated U-age-group check (Jonas is a currently
    15-year-old past the June cutoff, so the server tells him to play U17
    regardless of his group), and "MJT HS U13" skips that check's regex
    entirely and actually registers. Neither exercises the SJT/MJT split
    this test is for -- confirmed against the running server: selecting
    "HS U15" blocks with "Should play U17 or higher" and the SJT check never
    runs; "MJT HS U13" returns success. An SJT-named open_tournament() with
    an adult class (HS B, no U-prefix, no age relevance) isolates the actual
    rule under test: the SJT check log line and its message both fire.
    """
    name = seed.open_tournament(data_dir, name="Blocked SJT Cup")
    seed.komet_player(data_dir, "DEV-0003", "Jonas Junior", ["LEVEL 3-5"])
    sign_in_as(page, app_server, "jonas")
    page.goto(f"{app_server}/tournament.html?url={tournament_url(name)}")
    page.wait_for_load_state("networkidle")

    page.on("dialog", lambda d: d.accept())
    page.wait_for_selector("#register-section", state="visible")
    page.locator("select.singles-level").first.select_option("HS B")  # SJT, not MJT
    with page.expect_event("dialog"):
        page.click("#submit-btn")

    assert seed.registrations_for(data_dir, name) == [], "a LEVEL 3-5 player entered an SJT event"


def test_points_above_the_class_maximum_are_blocked(app_server, page, data_dir):
    """Elin Elit has DS 8000 points; class A's ds_max is 6000, so DS A must be
    refused. Both numbers are real: bwf_dev's persona and the point_rules seed."""
    name = seed.open_tournament(data_dir, name="Points Cup")
    sign_in_as(page, app_server, "elin")
    page.goto(f"{app_server}/tournament.html?url={tournament_url(name)}")
    page.wait_for_selector("#register-section", state="visible")

    page.on("dialog", lambda d: d.accept())
    page.locator("select.singles-level").first.select_option("DS A")
    with page.expect_event("dialog"):
        page.click("#submit-btn")

    assert seed.registrations_for(data_dir, name) == [], \
        "a player above the class maximum was allowed to register"


def test_non_komet_member_cannot_sign_in(app_server, page):
    """Pia is from another club. main's rule blocks her at login."""
    page.goto(f"{app_server}/")
    page.wait_for_selector("#devbar select")
    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.accept()))
    # select_option() dispatches the change event and returns; the login
    # POST and the alert() it triggers on failure both happen after that, in
    # devbar.js's async handler. Wait on the dialog itself, not a fixed
    # timeout, for the same race reason as the tests above.
    with page.expect_event("dialog"):
        page.locator("#devbar select").select_option("pia")

    assert any("Komet" in m for m in messages), "no message explaining the block"
