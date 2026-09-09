"""Tests for local development mode: state, endpoints and production guards."""

import inspect
import json
import os
import re
import sqlite3
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

import bwf_client


def _purge_dev_personas():
    """Remove every stub persona a dev login may have persisted.

    A plain `pytest` run has no DATA_DIR set, so app.PLAYERS_DB is the real
    players.db in the repo root. Without this, logging in as a persona injects
    a fake child into the BMK Komet roster and into the LEVEL 3-5 group that
    drives tournament visibility and reminder targeting.
    """
    import app
    conn = sqlite3.connect(app.PLAYERS_DB)
    conn.execute("DELETE FROM kometPlayers WHERE license_id LIKE 'DEV-%'")
    conn.execute("DELETE FROM players WHERE license_id LIKE 'DEV-%'")
    conn.commit()
    conn.close()


class TestModeState(unittest.TestCase):
    """Mode defaults to live and only moves when dev tools are enabled."""

    def setUp(self):
        bwf_client.set_mode("live")

    def tearDown(self):
        bwf_client.set_mode("live")

    def test_defaults_to_live(self):
        """A fresh process is in live mode."""
        self.assertEqual(bwf_client.get_mode(), "live")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_set_mode_to_dev(self):
        """With dev tools enabled the mode can be switched."""
        self.assertEqual(bwf_client.set_mode("dev"), "dev")
        self.assertEqual(bwf_client.get_mode(), "dev")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_mode_forced_live_without_dev_tools(self):
        """Without DEV_TOOLS the mode reads as live even if something set it."""
        bwf_client._mode = "dev"
        self.assertEqual(bwf_client.get_mode(), "live")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_rejects_unknown_mode(self):
        """An unknown mode is a programming error, not a silent no-op."""
        with self.assertRaises(ValueError):
            bwf_client.set_mode("banana")

    @patch.dict(os.environ, {}, clear=True)
    def test_dev_tools_disabled_by_default(self):
        self.assertFalse(bwf_client.dev_tools_enabled())

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_dev_tools_enabled_by_env(self):
        self.assertTrue(bwf_client.dev_tools_enabled())


class TestModeEndpoints(unittest.TestCase):
    """The toggle exists only on a server started with DEV_TOOLS."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        bwf_client.set_mode("live")

    def tearDown(self):
        bwf_client.set_mode("live")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_returns_404_in_production(self):
        """Production does not advertise a feature it does not have."""
        self.assertEqual(self.client.get("/api/dev-mode").status_code, 404)

    @patch.dict(os.environ, {}, clear=True)
    def test_post_returns_404_in_production(self):
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(bwf_client.get_mode(), "live")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_get_reports_state(self):
        resp = self.client.get("/api/dev-mode")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"dev_tools": True, "mode": "live"})

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_post_switches_mode_without_admin_session(self):
        """No admin check: the 404 gate above is the only access control, and
        session["admin"] is only ever set by a real Badminton Sweden login --
        requiring it here would make the switch unreachable on a machine with
        no real credentials, which defeats the point of dev mode."""
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["mode"], "dev")
        self.assertEqual(bwf_client.get_mode(), "dev")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_post_switches_mode_for_admin(self):
        """An admin session works too -- the removal of the admin *requirement*
        does not make an admin session harmful."""
        with self.client.session_transaction() as sess:
            sess["admin"] = True
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["mode"], "dev")
        self.assertEqual(bwf_client.get_mode(), "dev")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_post_rejects_unknown_mode(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = True
        resp = self.client.post("/api/dev-mode", json={"mode": "banana"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(bwf_client.get_mode(), "live")


class TestOpenTournamentsFakeFlag(unittest.TestCase):
    """/api/open-tournaments tags a row "_fake" by provenance (the dev.local
    host bwf_dev's fixtures always use -- see bwf_dev.py:109,122,135,148), not
    by whichever mode happens to be active at request time. Keying it off the
    live mode instead would invert the marker: a real tournament synced while
    dev mode was on would get a FAKE badge, and a dev fixture would lose its
    badge the moment someone flips the toggle back to live."""

    DEV_URL = "https://dev.local/test-fake-flag-tournament"
    REAL_URL = "https://badmintonsweden.tournamentsoftware.com/tournament/test-fake-flag-real"

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        self.app = app
        bwf_client.set_mode("live")
        self._insert(self.DEV_URL, "Fake Flag Test Tournament (dev.local)")
        self._insert(self.REAL_URL, "Fake Flag Test Tournament (real host)")

    def tearDown(self):
        bwf_client.set_mode("live")
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute("DELETE FROM tournaments WHERE tournament_url IN (?, ?)",
                     (self.DEV_URL, self.REAL_URL))
        conn.commit()
        conn.close()

    def _insert(self, url, name):
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute("DELETE FROM tournaments WHERE tournament_url = ?", (url,))
        conn.execute(
            "INSERT INTO tournaments "
            "(tournament_url, tournament_name, location, date_start, date_end, selected_for_view) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (url, name, "Testville", "2099-01-01", "2099-01-02"),
        )
        conn.commit()
        conn.close()

    def _fetch_row(self, url):
        resp = self.client.get("/api/open-tournaments")
        self.assertEqual(resp.status_code, 200)
        rows = resp.get_json()["tournaments"]
        return next(t for t in rows if t["url"] == url)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_dev_local_row_is_tagged_fake_in_dev_mode(self):
        bwf_client.set_mode("dev")
        self.assertTrue(self._fetch_row(self.DEV_URL)["_fake"])

    def test_dev_local_row_is_not_listed_at_all_in_live_mode(self):
        """Superseded the "tagged in either mode" case: fixtures are now filtered
        out of live listings entirely, so there is no row left to tag. Tagging by
        provenance still matters for the rows that DO appear."""
        bwf_client.set_mode("live")
        rows = self.client.get("/api/open-tournaments").get_json()["tournaments"]
        self.assertNotIn(self.DEV_URL, [t["url"] for t in rows])

    def test_real_row_is_never_tagged_fake(self):
        bwf_client.set_mode("live")
        self.assertFalse(self._fetch_row(self.REAL_URL)["_fake"])


class TestFakeData(unittest.TestCase):
    """Fixtures must exercise the domain rules and must not rot over time."""

    def test_fixture_dates_are_iso_format(self):
        """Every date is YYYY-MM-DD. This alone doesn't prove the dates are
        relative to today (a hardcoded date matches the same regex) -- the
        future/past tests below are what prove that."""
        import bwf_dev
        for tournament in bwf_dev.TOURNAMENTS:
            for key in ("registration_closes", "competition_start", "cancellation_deadline"):
                value = tournament[key]
                self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$", f"{key} is not a date")

    def test_open_tournament_deadline_is_in_the_future(self):
        import bwf_dev
        from datetime import date
        open_t = next(t for t in bwf_dev.TOURNAMENTS if t["fixture"] == "open")
        self.assertGreater(date.fromisoformat(open_t["registration_closes"]), date.today())

    def test_closed_tournament_deadline_is_in_the_past(self):
        import bwf_dev
        from datetime import date
        closed = next(t for t in bwf_dev.TOURNAMENTS if t["fixture"] == "closed")
        self.assertLess(date.fromisoformat(closed["registration_closes"]), date.today())

    def test_has_an_sjt_tournament(self):
        import bwf_dev
        self.assertTrue(any("SJT" in t["name"].upper() for t in bwf_dev.TOURNAMENTS))

    def test_personas_cover_the_age_rules(self):
        """An under-13, a junior and an adult must all exist."""
        import bwf_dev
        from datetime import date
        ages = []
        for p in bwf_dev.PLAYERS:
            if not p["dob"]:
                continue
            born = date.fromisoformat(p["dob"])
            today = date.today()
            ages.append(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
        self.assertTrue(any(a < 13 for a in ages), "no under-13 persona")
        self.assertTrue(any(13 <= a < 18 for a in ages), "no junior persona")
        self.assertTrue(any(a >= 18 for a in ages), "no adult persona")

    def test_personas_cover_the_mjt_sjt_split(self):
        import bwf_dev
        groups = {g for p in bwf_dev.PLAYERS for g in p.get("groups", [])}
        self.assertIn("LEVEL 3-5", groups)
        self.assertIn("LEVEL_6", groups)

    def test_every_player_is_marked_fake(self):
        import bwf_dev
        for p in bwf_dev.PLAYERS:
            self.assertTrue(p["_fake"])


class TestStubs(unittest.TestCase):
    """Stubs mirror the live signatures and never touch the network."""

    def setUp(self):
        self.env = patch.dict(os.environ, {"DEV_TOOLS": "1"})
        self.env.start()
        bwf_client.set_mode("dev")

    def tearDown(self):
        bwf_client.set_mode("live")
        self.env.stop()

    def test_login_accepts_any_password_for_known_persona(self):
        result = bwf_client.login("jonas", "anything")
        self.assertEqual(result["player_name"], "Jonas Junior")
        self.assertTrue(result["_fake"])

    def test_login_rejects_unknown_username(self):
        self.assertIsNone(bwf_client.login("who-is-this", "anything"))

    def test_login_rejects_empty_password(self):
        self.assertIsNone(bwf_client.login("jonas", ""))

    def test_search_players_matches_substring(self):
        results = bwf_client.search_players("Junior")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["license_id"], "DEV-0003")

    def test_get_player_ranking_returns_json_string(self):
        """Same type trap as live: a JSON string, not a dict."""
        raw = bwf_client.get_player_ranking("Adam Adult")
        self.assertIsInstance(raw, str)
        self.assertEqual(json.loads(raw)["HS"]["points"], "1500")

    def test_fetch_tournament_info_returns_all_date_keys(self):
        info = bwf_client.fetch_tournament_info("https://dev.local/tournament/DEV-T1")
        for key in ("registration_opens", "registration_closes", "cancellation_deadline",
                    "competition_start", "competition_end", "name", "levels"):
            self.assertIn(key, info)

    def test_submit_registrations_reports_success_without_playwright(self):
        result = bwf_client.submit_registrations("Dev Open (FAKE)", "sbf04959", "pw")
        self.assertTrue(result["success"])
        self.assertIn("submitted", result)
        self.assertTrue(result["_fake"])

    def test_submit_registrations_entries_have_the_fields_the_templates_read(self):
        """manage-tournaments.html and tournament.html do p.player_name and
        p.message per entry -- a list of bare names renders 'undefined'."""
        result = bwf_client.submit_registrations("Dev Open (FAKE)", "sbf04959", "pw")
        entry = result["submitted"][0]
        self.assertIsInstance(entry, dict)
        for key in ("player_name", "license_id", "message"):
            self.assertIn(key, entry)

    def test_get_tournament_events_accepts_and_ignores_session(self):
        """bwf_live's get_tournament_events(tournament_id, session=None) --
        the stub must accept the same call shape."""
        result = bwf_client.get_tournament_events("DEV-T1", session=object())
        self.assertTrue(result["_fake"])
        self.assertIn("HS A", result["singles_levels"])

    def test_get_tournament_events_includes_the_levels_key(self):
        """bwf_live always returns "levels" (bwf_live.py:591) -- a caller
        that reads it unconditionally, as _fetch_tournament does, would
        KeyError without it."""
        result = bwf_client.get_tournament_events("DEV-T1")
        self.assertIn("levels", result)
        self.assertIsInstance(result["levels"], list)

    def test_get_tournament_player_results_matches_live_field_names(self):
        """tournament_detail.html reads s.category/played/win_loss/sets/points
        and m.round/event/team1/team2/team1_won/score."""
        result = bwf_client.get_tournament_player_results("T-1", "P-1")
        stat = result["stats"][0]
        for key in ("category", "played", "win_loss", "sets", "points"):
            self.assertIn(key, stat)
        match = result["matches"][0]
        for key in ("round", "event", "team1", "team2", "team1_won", "score"):
            self.assertIn(key, match)

    def test_get_player_ranking_by_profile_unknown_is_falsy(self):
        """app.py:2762 does `if ranking_data:` -- {"_fake": True} is truthy
        and would falsely log a ranking as found."""
        result = bwf_client.get_player_ranking_by_profile("/player-profile/NOPE")
        self.assertEqual(result, {})
        self.assertFalse(result)

    def test_get_player_profile_by_license_ranking_is_a_json_string(self):
        """A different shape from get_player_ranking's: singles/doubles/mixed
        buckets with int rank/points, matching bwf_live's
        _scrape_ranking_from_page output."""
        profile = bwf_client.get_player_profile_by_license("DEV-0001")
        ranking = json.loads(profile["ranking"])
        self.assertEqual(ranking["singles"]["HS"]["points"], 1500)
        self.assertTrue(profile["_fake"])

    def test_get_player_profile_by_license_unknown_returns_none(self):
        self.assertIsNone(bwf_client.get_player_profile_by_license("NOPE"))

    def test_no_network_library_imported(self):
        """The absence of a network import is what makes a no-network guard
        meaningful: if bwf_dev ever reaches for requests/urllib/httpx/
        playwright (directly or via bwf_submit, which launches a real
        browser), that's a bug, and this test is the tripwire."""
        import bwf_dev
        forbidden = {"requests", "urllib", "urllib3", "httpx", "http.client",
                     "socket", "playwright", "bwf_submit"}
        self.assertFalse(forbidden & set(bwf_dev.__dict__.keys()))
        with open(bwf_dev.__file__, encoding="utf-8") as f:
            source = f.read()
        for lib in ("requests", "urllib", "httpx", "playwright", "bwf_submit"):
            self.assertNotIn(f"import {lib}", source)


class TestGuards(unittest.TestCase):
    """The properties that make dev mode trustworthy."""

    def test_app_py_bwf_urls_are_limited_to_the_two_known_lookups(self):
        """_register_partner's short-partner-name safeguard (searches by
        licence ID) and player_details' `if not profile_url:` branch
        (resolves a player name to a profile URL) are the plan's one
        deliberate exemption: the plan considered extracting both behind
        bwf_client, declined to expand scope, and left them named here
        instead of silently weakening this guard. Both are NOT interceptable
        in dev mode -- dev mode will hit the live Badminton Sweden site
        through them. Any new tournamentsoftware.com reference, or one of
        these two moved to a third place, fails this test."""
        with open("app.py", encoding="utf-8") as f:
            lines = f.readlines()

        occurrence_lines = [i for i, line in enumerate(lines) if "tournamentsoftware.com" in line]

        def enclosing_function(line_index):
            for i in range(line_index, -1, -1):
                if lines[i].startswith("def "):
                    return lines[i][len("def "):].split("(")[0]
            return None

        counts = {}
        for i in occurrence_lines:
            name = enclosing_function(i)
            counts[name] = counts.get(name, 0) + 1

        self.assertEqual(
            counts, {"_register_partner": 1, "player_details": 2},
            f"tournamentsoftware.com occurrences moved or changed count "
            f"(found at lines {[i + 1 for i in occurrence_lines]}, inside {counts})")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_bwf_client_functions_complete_without_network_in_dev_mode(self):
        """With every HTTP entry point armed to explode, every one of
        bwf_live's 18 public functions still completes, end to end, through
        bwf_client in dev mode.

        This calls bwf_client's functions directly -- it never goes through a
        Flask route. That is a real gap, not an oversight: two lookups inside
        app.py routes (player_details' `if not profile_url:` branch and
        _register_partner's short-name safeguard) call the live site directly
        and are reachable in dev mode. See
        test_player_details_name_lookup_leaks_to_the_live_site_in_dev_mode
        below, which proves that gap rather than assuming it away."""
        bwf_client.set_mode("dev")
        try:
            def explode(*args, **kwargs):
                raise AssertionError("dev mode attempted a network call")

            with patch("requests.get", explode), patch("requests.post", explode), \
                 patch("requests.Session", explode):
                self.assertEqual(bwf_client.get_player_license("Adam Adult"), "DEV-0001")
                self.assertTrue(bwf_client.get_player_ranking("Adam Adult"))
                self.assertTrue(bwf_client.verify_credentials("adam", "anything"))
                self.assertIsNotNone(bwf_client.login("adam", "anything"))
                self.assertTrue(bwf_client.search_players("Adam"))
                self.assertTrue(bwf_client.get_player_details("/player-profile/DEV-0001"))
                self.assertTrue(bwf_client.get_player_ranking_by_profile("/player-profile/DEV-0001"))
                self.assertTrue(bwf_client.get_player_profile_by_license("DEV-0001"))
                self.assertTrue(bwf_client.get_tournament_events("DEV-T1"))
                self.assertTrue(bwf_client.fetch_tournament_info("https://dev.local/tournament/DEV-T1"))
                self.assertTrue(bwf_client.fetch_tournament_details("https://dev.local/tournament/DEV-T1"))
                self.assertTrue(bwf_client.search_tournaments("", "", ""))
                self.assertTrue(bwf_client.list_all_tournaments("", ""))
                self.assertTrue(bwf_client.get_tournament_medals("DEV-T1"))
                self.assertEqual(bwf_client.get_tournament_player_id("DEV-T1", "Adam Adult"), "DEV-0001")
                self.assertTrue(bwf_client.get_tournament_player_results("DEV-T1", "DEV-0001"))
                self.assertTrue(bwf_client.get_tournament_clubs("DEV-T1"))
                self.assertTrue(bwf_client.submit_registrations("Dev Open (FAKE)", "sbf04959", "pw")["success"])
        finally:
            bwf_client.set_mode("live")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_player_details_name_lookup_leaks_to_the_live_site_in_dev_mode(self):
        """Pins a known, accepted gap rather than assuming it away.

        player_details' `if not profile_url:` branch (app.py, around line
        3550) calls ext_requests directly, bypassing bwf_client entirely, so
        a name-only lookup reaches Badminton Sweden even in dev mode. This is
        reachable in practice: /api/search-players merges local-DB rows that
        carry no profile_url, and templates/tournament.html falls back to
        `name=` whenever profile_url is falsy. With requests.Session armed to
        raise, the route-level call proves the leak actually happens instead
        of trusting that the two-lookup exemption documented elsewhere stays
        confined to what it claims."""
        import app
        app.app.config["TESTING"] = True
        client = app.app.test_client()
        bwf_client.set_mode("dev")
        try:
            def explode(*args, **kwargs):
                raise AssertionError("dev mode attempted a network call")

            with patch("requests.Session", explode):
                resp = client.get("/api/player-details?name=Adam+Adult")
                self.assertEqual(resp.status_code, 500)
                self.assertIn("dev mode attempted a network call", resp.get_json()["error"])
        finally:
            bwf_client.set_mode("live")

    @patch.dict(os.environ, {}, clear=True)
    def test_production_cannot_be_switched_into_dev(self):
        """With DEV_TOOLS unset, get_mode() reads live no matter what --
        even a direct mutation of the internal state -- and the switch
        endpoint itself does not exist."""
        bwf_client._mode = "dev"
        try:
            self.assertEqual(bwf_client.get_mode(), "live")

            import app
            app.app.config["TESTING"] = True
            client = app.app.test_client()
            resp = client.post("/api/dev-mode", json={"mode": "dev"})
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(bwf_client.get_mode(), "live")
        finally:
            bwf_client._mode = "live"

    def test_bwf_dev_and_bwf_client_match_bwf_live_names_and_signatures(self):
        """A function added to bwf_live but missing -- or added with a
        different signature -- from bwf_dev or bwf_client fails here, not in
        production.

        This is a signature-only guard: it proves every public bwf_live
        function has a same-named, same-signature stub in bwf_dev AND a
        same-named, same-signature forwarder in bwf_client. It deliberately
        does NOT prove a bwf_client forwarder's *body* passes every argument
        through correctly -- this project has already shipped exactly that
        bug (bwf_client.get_tournament_events silently not passing `session`
        to the backend), and a signature comparison cannot catch it, because
        the signature was already correct; only the two lines being different
        was the bug. Catching that class of bug is
        test_get_tournament_events_accepts_and_ignores_session's job, not
        this test's. What this test catches is the cheaper, more common
        mistake: adding a function to bwf_live and bwf_dev and forgetting the
        bwf_client forwarder entirely, which would otherwise stay green here
        until an AttributeError at runtime."""
        import bwf_dev
        import bwf_live

        def public_functions(module):
            return {name: obj for name, obj in vars(module).items()
                    if not name.startswith("_") and inspect.isfunction(obj)
                    and obj.__module__ == module.__name__}

        live_funcs = public_functions(bwf_live)
        dev_funcs = public_functions(bwf_dev)
        client_funcs = public_functions(bwf_client)

        missing_dev = set(live_funcs) - set(dev_funcs)
        self.assertEqual(missing_dev, set(), f"bwf_dev is missing stubs for: {missing_dev}")

        missing_client = set(live_funcs) - set(client_funcs)
        self.assertEqual(missing_client, set(), f"bwf_client is missing forwarders for: {missing_client}")

        def signature_drift(other_funcs):
            return {
                name: (str(inspect.signature(live_funcs[name])), str(inspect.signature(other_funcs[name])))
                for name in live_funcs
                if name in other_funcs
                and str(inspect.signature(live_funcs[name])) != str(inspect.signature(other_funcs[name]))
            }

        self.assertEqual(signature_drift(dev_funcs), {}, "bwf_dev signature drift from bwf_live")
        self.assertEqual(signature_drift(client_funcs), {}, "bwf_client signature drift from bwf_live")

    def test_bwf_live_and_bwf_client_do_not_import_flask_or_sqlite3(self):
        """The boundary must stay swappable behind the mode switch. If
        bwf_live or bwf_client ever imports Flask (request/session state) or
        sqlite3 (database writes), the separation the whole design exists to
        keep -- app.py owns Flask and the database, bwf_live/bwf_client own
        neither -- has been undone."""
        pattern = re.compile(r"^\s*(?:import|from)\s+(flask|sqlite3)\b", re.MULTILINE)
        for module_name in ("bwf_live.py", "bwf_client.py"):
            with open(module_name, encoding="utf-8") as f:
                source = f.read()
            matches = pattern.findall(source)
            self.assertEqual(matches, [], f"{module_name} imports: {matches}")


class TestDevLoginPersistsGroups(unittest.TestCase):
    """_persist_login_profile (app.py) writes a dev persona's "groups" to
    kometPlayers.groups, but only in dev mode -- see Task 4 of the final fix
    wave. Before this, bwf_dev.py set "groups" on every persona and nothing
    ever read it: logging in as Jonas Junior (groups=["LEVEL 3-5"]) never
    actually made him a LEVEL 3-5 player, so the MJT/SJT group-visibility
    rules were never exercisable through a dev login, even though
    test_personas_cover_the_mjt_sjt_split (TestFakeData) passed the whole
    time -- it only ever asserted strings in a dict nothing read."""

    LICENSE_ID = "DEV-0003"  # Jonas Junior, groups=["LEVEL 3-5"]

    def setUp(self):
        import app
        self.app = app
        bwf_client.set_mode("live")
        self._delete_komet_row()

    def tearDown(self):
        bwf_client.set_mode("live")
        self._delete_komet_row()

    def _delete_komet_row(self):
        conn = sqlite3.connect(self.app.PLAYERS_DB)
        conn.execute("DELETE FROM kometPlayers WHERE license_id = ?", (self.LICENSE_ID,))
        conn.commit()
        conn.close()

    def _groups_in_db(self):
        conn = sqlite3.connect(self.app.PLAYERS_DB)
        cur = conn.execute("SELECT groups FROM kometPlayers WHERE license_id = ?", (self.LICENSE_ID,))
        row = cur.fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else None

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_dev_login_as_level_3_5_persona_lands_groups_in_kometplayers(self):
        bwf_client.set_mode("dev")
        try:
            profile = bwf_client.login("jonas", "anything")
            self.assertEqual(profile["club"], "BMK Komet")
            self.app._persist_login_profile(profile)
            self.assertEqual(self._groups_in_db(), ["LEVEL 3-5"])
        finally:
            bwf_client.set_mode("live")

    def test_live_mode_login_writes_no_groups(self):
        """Guarded on bwf_client.get_mode() == "dev", not merely on the
        "groups" key's presence -- a real login profile never carries that
        key, but the explicit mode check means even a profile that somehow
        did would not persist it outside dev mode."""
        bwf_client.set_mode("live")
        profile = {
            "player_name": "Live Persona", "license_id": self.LICENSE_ID,
            "club": "BMK Komet", "gender": "M", "email": "live@example.test",
            "phone": "", "dob": "", "age": "", "ranking": {},
            "profile_url": "/player-profile/DEV-0003", "is_club_account": False,
            "groups": ["LEVEL 3-5"],
        }
        self.app._persist_login_profile(profile)
        self.assertIsNone(self._groups_in_db())


class TestRegisterPartnerRankingIsClean(unittest.TestCase):
    """The one players.ranking write path a dev-mode change touched
    (_register_partner, via bwf_client.get_player_ranking_by_profile) had
    only ever been verified by a throwaway script -- see Task 6 of the final
    fix wave. Assert what actually lands in the column: the dev fixture's own
    rank/points, with no "_fake" key smuggled in as a pseudo-category."""

    LICENSE_ID = "DEV-0006"  # Pia Partner
    TOURNAMENT_NAME = "Fix-Wave Test Cup"

    def setUp(self):
        import app
        self.app = app
        bwf_client.set_mode("live")
        self._delete()

    def tearDown(self):
        bwf_client.set_mode("live")
        self._delete()

    def _delete(self):
        conn = sqlite3.connect(self.app.PLAYERS_DB)
        conn.execute("DELETE FROM players WHERE license_id = ?", (self.LICENSE_ID,))
        conn.commit()
        conn.close()
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute("DELETE FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?",
                     (self.TOURNAMENT_NAME, self.LICENSE_ID))
        conn.commit()
        conn.close()

    def _ranking_in_db(self):
        conn = sqlite3.connect(self.app.PLAYERS_DB)
        cur = conn.execute("SELECT ranking FROM players WHERE license_id = ?", (self.LICENSE_ID,))
        row = cur.fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else None

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_register_partner_persists_a_clean_ranking_in_dev_mode(self):
        bwf_client.set_mode("dev")
        try:
            self.app._register_partner(
                tournament_name=self.TOURNAMENT_NAME,
                partner_license_id=self.LICENSE_ID,
                partner_name="Pia Partner",
                partner_club="Grannklubben",
                partner_profile_url="/player-profile/DEV-0006",
            )
            ranking = self._ranking_in_db()
            self.assertIsNotNone(ranking, "no ranking was persisted")
            self.assertNotIn("_fake", ranking)
            self.assertEqual(ranking, {
                "DD": {"rank": "300", "points": "800"},
                "MD": {"rank": "310", "points": "780"},
            })
        finally:
            bwf_client.set_mode("live")


if __name__ == "__main__":
    unittest.main()


class TestDevPersonasEndpoint(unittest.TestCase):
    """The login page's test-account picker is served only to a dev-mode server."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        bwf_client.set_mode("live")
        _purge_dev_personas()

    def tearDown(self):
        bwf_client.set_mode("live")
        _purge_dev_personas()

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_404_in_production(self):
        """Production must not advertise the picker at all."""
        self.assertEqual(self.client.get("/api/dev-personas").status_code, 404)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_returns_no_personas_in_live_mode(self):
        """These usernames only resolve against the stubs, so live mode offers none."""
        resp = self.client.get("/api/dev-personas")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["mode"], "live")
        self.assertEqual(body["personas"], [])

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_lists_every_persona_in_dev_mode(self):
        import bwf_dev
        bwf_client.set_mode("dev")
        body = self.client.get("/api/dev-personas").get_json()
        self.assertEqual(len(body["personas"]), len(bwf_dev.PLAYERS))
        usernames = {p["username"] for p in body["personas"]}
        self.assertEqual(usernames, {p["username"] for p in bwf_dev.PLAYERS})

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_every_persona_carries_a_description(self):
        """The picker is useless without them - that is the point of the feature."""
        bwf_client.set_mode("dev")
        for p in self.client.get("/api/dev-personas").get_json()["personas"]:
            self.assertTrue(p["description"].strip(), f"{p['username']} has no description")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_a_listed_persona_can_actually_log_in(self):
        """Pins the contract the picker depends on: username in, session out."""
        bwf_client.set_mode("dev")
        personas = self.client.get("/api/dev-personas").get_json()["personas"]
        target = next(p for p in personas if p["username"] == "mini")
        resp = self.client.post("/api/bwf-login",
                                json={"login": target["username"], "password": "dev"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["player_name"], target["player_name"])


class TestModeSwitchSignsOut(unittest.TestCase):
    """A session belongs to the backend that created it, so a mode change ends it."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        bwf_client.set_mode("live")
        _purge_dev_personas()

    def tearDown(self):
        bwf_client.set_mode("live")
        _purge_dev_personas()

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_switching_to_dev_clears_a_live_session(self):
        with self.client.session_transaction() as sess:
            sess["bwf_login"] = "realuser"
            sess["bwf_player"] = "Real Person"
            sess["admin"] = True
            # What a real login stamps. Sessions without it predate the stamp
            # and are deliberately grandfathered rather than dropped.
            sess["bwf_mode"] = "live"
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertTrue(resp.get_json()["signed_out"])
        # The switch reports it; _drop_session_from_another_mode() performs it
        # on the next request, before any handler can act on the stale session.
        self.client.get("/api/bwf-status")
        with self.client.session_transaction() as sess:
            self.assertNotIn("bwf_login", sess)
            self.assertNotIn("admin", sess)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_switching_to_live_clears_a_dev_session(self):
        """The direction the user hit: a stub persona must not survive into live."""
        bwf_client.set_mode("dev")
        self.client.post("/api/bwf-login", json={"login": "mini", "password": "dev"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["bwf_login"], "mini")
        resp = self.client.post("/api/dev-mode", json={"mode": "live"})
        self.assertTrue(resp.get_json()["signed_out"])
        self.client.get("/api/bwf-status")
        with self.client.session_transaction() as sess:
            self.assertNotIn("bwf_login", sess)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_posting_the_same_mode_keeps_the_session(self):
        """Only a real change signs out; a no-op POST must not."""
        with self.client.session_transaction() as sess:
            sess["bwf_login"] = "realuser"
        resp = self.client.post("/api/dev-mode", json={"mode": "live"})
        self.assertFalse(resp.get_json()["signed_out"])
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["bwf_login"], "realuser")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_switching_without_a_session_reports_no_sign_out(self):
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertFalse(resp.get_json()["signed_out"])


class TestSessionCannotCrossModes(unittest.TestCase):
    """A session is invalidated when the server's mode moves away from the one
    that created it. Enforced per-request rather than only in the switch
    handler, so it also covers sessions the switching client cannot see: other
    tabs and browsers, and a server restart (which resets the mode to "live"
    while the signed cookie survives, since app.secret_key is constant)."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        bwf_client.set_mode("live")
        _purge_dev_personas()

    def tearDown(self):
        bwf_client.set_mode("live")
        _purge_dev_personas()

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_a_dev_session_is_dropped_once_the_mode_is_live(self):
        """The restart case: signed in under the stubs, server now live."""
        bwf_client.set_mode("dev")
        self.client.post("/api/bwf-login", json={"login": "sbf04959", "password": "dev"})
        with self.client.session_transaction() as sess:
            self.assertTrue(sess["admin"])
            self.assertEqual(sess["bwf_mode"], "dev")

        # Mode moves without this client posting the switch itself.
        bwf_client.set_mode("live")
        self.client.get("/api/bwf-status")

        with self.client.session_transaction() as sess:
            self.assertNotIn("bwf_login", sess)
            self.assertNotIn("admin", sess)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_a_live_session_is_dropped_once_the_mode_is_dev(self):
        with self.client.session_transaction() as sess:
            sess["bwf_login"] = "realuser"
            sess["admin"] = True
            sess["bwf_mode"] = "live"
        bwf_client.set_mode("dev")
        self.client.get("/api/bwf-status")
        with self.client.session_transaction() as sess:
            self.assertNotIn("bwf_login", sess)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_a_session_in_the_matching_mode_survives(self):
        bwf_client.set_mode("dev")
        self.client.post("/api/bwf-login", json={"login": "adam", "password": "dev"})
        self.client.get("/api/bwf-status")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["bwf_login"], "adam")

    @patch.dict(os.environ, {}, clear=True)
    def test_production_never_drops_a_session(self):
        """With DEV_TOOLS unset the guard must not run at all."""
        with self.client.session_transaction() as sess:
            sess["bwf_login"] = "realuser"
            sess["bwf_mode"] = "dev"   # nonsense value; production must ignore it
        self.client.get("/api/bwf-status")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["bwf_login"], "realuser")


class TestFixturesDoNotLeakIntoLive(unittest.TestCase):
    """Dev fixtures are written into the same local tournaments.db as real
    tournaments. Without a provenance filter they keep appearing after a switch
    back to live -- and worse, they satisfy the "already fetched today" cache
    check in /api/bwf-tournaments-all, so live mode serves fixtures and never
    calls the real site at all. Found by using the app, not by a test."""

    FIXTURE_URL = "https://dev.local/tournament/DEV-T1"
    REAL_URL = "https://badmintonsweden.tournamentsoftware.com/tournament/REAL-1"

    def setUp(self):
        import app
        self.app = app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        bwf_client.set_mode("live")
        self._reset_rows()

    def tearDown(self):
        bwf_client.set_mode("live")
        self._reset_rows()

    def _reset_rows(self):
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute("DELETE FROM tournaments WHERE tournament_url IN (?, ?)",
                     (self.FIXTURE_URL, self.REAL_URL))
        conn.commit()
        conn.close()

    def _insert(self, url, name, start):
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute(
            "INSERT INTO tournaments (tournament_name, tournament_url, date_start, "
            "selected_for_view) VALUES (?, ?, ?, 1)", (name, url, start))
        conn.commit()
        conn.close()

    def _names(self):
        body = self.client.get("/api/open-tournaments").get_json()
        return {t["name"] for t in body["tournaments"]}

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_live_mode_hides_fixtures_and_shows_real(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        self._insert(self.FIXTURE_URL, "Dev Open (FAKE)", future)
        self._insert(self.REAL_URL, "Real Cup", future)
        self.assertEqual(self._names() & {"Dev Open (FAKE)", "Real Cup"}, {"Real Cup"})

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_dev_mode_hides_real_and_shows_fixtures(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        self._insert(self.FIXTURE_URL, "Dev Open (FAKE)", future)
        self._insert(self.REAL_URL, "Real Cup", future)
        bwf_client.set_mode("dev")
        self.assertEqual(self._names() & {"Dev Open (FAKE)", "Real Cup"}, {"Dev Open (FAKE)"})

    @patch.dict(os.environ, {}, clear=True)
    def test_production_shows_real_tournaments(self):
        """The filter must never hide a real tournament in production."""
        future = (date.today() + timedelta(days=30)).isoformat()
        self._insert(self.REAL_URL, "Real Cup", future)
        self.assertIn("Real Cup", self._names())

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_fixtures_do_not_satisfy_the_live_cache_check(self):
        """The bug as hit: a fixture cached today made live mode skip the fetch."""
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        conn.execute(
            "INSERT INTO tournaments (tournament_name, tournament_url, date_start, "
            "last_updated) VALUES (?, ?, ?, ?)",
            ("Dev Open (FAKE)", self.FIXTURE_URL,
             (date.today() + timedelta(days=30)).isoformat(),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        clause, params = self.app._mode_url_clause()
        conn = sqlite3.connect(self.app.TOURNAMENTS_DB)
        today = date.today().strftime("%Y-%m-%d")
        count = conn.execute(
            f"SELECT COUNT(*) FROM tournaments WHERE last_updated LIKE ? AND {clause}",
            (f"{today}%",) + params).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0, "a dev fixture counted as live cache")
