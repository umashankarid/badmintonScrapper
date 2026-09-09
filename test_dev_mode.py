"""Tests for local development mode: state, endpoints and production guards."""

import json
import os
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
    def test_post_requires_admin(self):
        """Switching mode is a mutating action, like every other admin endpoint."""
        resp = self.client.post("/api/dev-mode", json={"mode": "dev"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(bwf_client.get_mode(), "live")

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_post_switches_mode_for_admin(self):
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


if __name__ == "__main__":
    unittest.main()
