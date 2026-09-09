"""Tests for local development mode: state, endpoints and production guards."""

import inspect
import json
import os
import re
import sqlite3
import unittest
from unittest.mock import patch

import bwf_client


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

    def test_dev_local_row_is_tagged_fake_in_either_mode(self):
        bwf_client.set_mode("live")
        self.assertTrue(self._fetch_row(self.DEV_URL)["_fake"])
        bwf_client.set_mode("dev")
        self.assertTrue(self._fetch_row(self.DEV_URL)["_fake"])

    def test_real_row_is_never_tagged_fake(self):
        bwf_client.set_mode("live")
        self.assertFalse(self._fetch_row(self.REAL_URL)["_fake"])
        bwf_client.set_mode("dev")
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
