"""Tests for local development mode: state, endpoints and production guards."""

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


if __name__ == "__main__":
    unittest.main()
