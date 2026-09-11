"""The admin journey: make a tournament visible, see who registered."""

from tests.e2e import seed
from tests.e2e.conftest import console_errors
from tests.e2e.test_player import sign_in_as


def test_admin_sees_registrations_for_a_tournament(app_server, page, data_dir):
    """/api/tournament-players resolves the display name with
    COALESCE(p.name, 'Unknown') via a LEFT JOIN on players.db's `players`
    table -- seed.registration() alone leaves that side of the join empty
    (by design, see seed.player()'s docstring), so without seeding the
    player row too, an admin would see "Unknown" and this assertion would
    never have proven anything."""
    name = seed.open_tournament(data_dir, name="Admin View Cup")
    seed.player(data_dir, "DEV-0001", "Adam Adult")
    seed.registration(data_dir, name, "DEV-0001", singles="HS A")
    sign_in_as(page, app_server, "sbf04959")     # the club account is an admin

    page.goto(f"{app_server}/tournament.html?url={seed.tournament_url(name)}")
    page.wait_for_load_state("networkidle")

    # get_by_text("Adam Adult") is ambiguous: the devbar's persona <option>
    # carries the same text as the registration row it's meant to find, so
    # scope to the table cell specifically (Playwright's own strict-mode
    # error names this exact locator as the unambiguous alternative).
    assert page.get_by_role("cell", name="Adam Adult").is_visible(), \
        "an admin could not see an existing registration"


def test_home_page_lists_only_visible_tournaments(app_server, page, data_dir):
    """selected_for_view is what the home page filters on. index.html hides
    the tournaments list behind a login form for anonymous visitors and only
    fetches /api/open-tournaments into a visible container once
    checkBwfStatus() confirms a session (templates/index.html:62-87) -- a
    bare page.goto("/") here would just be asserting against the login
    page's own text, so sign in first.

    "Old Cup" is excluded by date, not by the flag -- seed.py hardcoded
    selected_for_view=1 for every fixture until it became a parameter, so
    that exclusion alone never actually proved the flag itself does
    anything. "Hidden Cup" is the real negative case: visible=0, but
    otherwise identical to "Visible Cup" (open registration, future
    competition), so only the flag can be excluding it.
    """
    visible = seed.open_tournament(data_dir, name="Visible Cup")
    seed.past_tournament(data_dir, name="Old Cup")
    hidden = seed.open_tournament(data_dir, name="Hidden Cup", selected_for_view=0)

    with console_errors(page) as errors:
        sign_in_as(page, app_server, "sbf04959")
        # sign_in_as only waits for the post-login redirect to land on "/";
        # unlike every other caller here, this test never does its own
        # page.goto() afterward, so it still needs to wait for that fresh
        # document's own checkBwfStatus() -> /api/open-tournaments fetch
        # to finish before reading the rendered list below.
        page.wait_for_load_state("networkidle")

    body = page.locator("body").inner_text()
    assert visible in body
    assert "Old Cup" not in body, "a past tournament was listed"
    assert hidden not in body, "a tournament with selected_for_view=0 was listed"
    assert errors == []


def test_admin_can_hide_a_tournament_from_the_home_page(app_server, page, data_dir):
    """selected_for_view is what /api/open-tournaments filters the home page on
    (app.py:open_tournaments). The brief called /api/tournament-visibility/toggle
    directly -- read against app.py's toggle_tournament_visibility, that endpoint
    writes a completely different thing: a "visible" flag in the ADMIN_DB
    tournament_visibility table, keyed by a "db" file, used for imported BWF
    tournament databases. It never touches tournaments.selected_for_view, so it
    cannot make this assertion true regardless of payload shape.

    The real path an admin uses is add-remove-tournaments.html, which POSTs to
    /api/bwf-tournament-visibility/save (see saveSelection() in that template).
    Driving it through the UI: that page's "fetch tournaments from Badminton
    Sweden" call is same-day cached in tournaments.db (see get_all_bwf_tournaments's
    "already fetched today" check), and seed.py's inserts default last_updated to
    now, so this test's own seed call above already satisfies that cache and the
    page never reaches the network. Every dev-fixture tournament already in the
    (session-scoped) DB is listed, pre-checked to match its current
    selected_for_view. Unchecking only the target checkbox and saving re-affirms
    every other row's existing state and flips just this one -- safe regardless
    of what other tests seeded earlier in the session.

    stays_visible is a positive control: without it, the final body check
    would pass identically if the page 500'd or sign-in silently failed and
    the login screen rendered instead -- neither contains "Hide Me Cup"
    either. Same pairing as test_home_page_lists_only_visible_tournaments.
    """
    name = seed.open_tournament(data_dir, name="Hide Me Cup")
    stays_visible = seed.open_tournament(data_dir, name="Stay Visible Cup")
    sign_in_as(page, app_server, "sbf04959")

    with page.expect_response(lambda r: "/api/bwf-tournaments-all" in r.url):
        page.goto(f"{app_server}/add-remove-tournaments.html")

    selector = f'.bwf-tournament-checkbox[data-name="{name}"]'
    page.wait_for_selector(selector)
    checkbox = page.locator(selector)
    assert checkbox.is_checked(), "a freshly opened tournament should start visible"

    page.once("dialog", lambda d: d.accept())   # saveSelection()'s confirmation alert
    checkbox.uncheck()
    with page.expect_response(lambda r: "/api/bwf-tournament-visibility/save" in r.url):
        page.get_by_role("button", name="Save Selected Tournaments").click()

    row = next(r for r in seed.tournaments(data_dir) if r["tournament_name"] == name)
    assert row["selected_for_view"] == 0

    page.goto(f"{app_server}/")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    assert name not in body
    assert stays_visible in body, \
        "an unrelated tournament vanished too, or the page failed to render"


def test_orphaned_registration_cleanup_runs_from_the_database_page(isolated_app_server, page, tmp_path):
    """main added this button (f15fa35). An orphan is a registration whose
    licence has no matching player row.

    cleanup_orphaned_registrations (app.py:4272) is selective -- empty /
    ghost-player / non-Komet-main -- so a legitimate Komet registration is
    seeded alongside the orphan and asserted to survive: without it, an
    unconditional DELETE with no WHERE clause would pass this test
    identically to the real, selective cleanup.

    Runs against isolated_app_server, not the shared app_server/data_dir:
    the endpoint this test drives has no tournament scope at all -- it
    deletes ghost/empty/non-Komet registrations across every tournament in
    whatever database the server points at. Against the shared session
    database that would delete rows other tests own, and only survived
    because test_admin.py happened to sort before test_player.py; under
    pytest-randomly, -p xdist, --lf, or a -k selection it would not. A
    private app_server + DATA_DIR for just this test means the unscoped
    DELETE has nothing to reach but its own rows, regardless of order.
    """
    data_dir = tmp_path
    name = seed.open_tournament(data_dir, name="Orphan Cup")
    seed.registration(data_dir, name, "GHOST-1", singles="HS B")
    seed.player(data_dir, "DEV-0002", "Elin Elit")
    seed.registration(data_dir, name, "DEV-0002", singles="DS A")
    assert len(seed.registrations_for(data_dir, name)) == 2

    sign_in_as(page, isolated_app_server, "sbf04959")
    page.goto(f"{isolated_app_server}/manage-db.html")
    page.wait_for_load_state("networkidle")

    # networkidle after the click would race the fetch() the same way Task 4
    # found for same-page actions -- wait on the actual response instead.
    page.once("dialog", lambda d: d.accept())   # "Remove all empty/orphaned..."
    with page.expect_response(lambda r: "/api/cleanup-orphaned-registrations" in r.url):
        page.get_by_role("button", name="Clean Orphaned Registrations").click()

    remaining_ids = {r["license_id"] for r in seed.registrations_for(data_dir, name)}
    assert remaining_ids == {"DEV-0002"}, \
        "cleanup should remove only the orphan and keep the legitimate registration"
