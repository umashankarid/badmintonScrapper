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


if __name__ == "__main__":
    unittest.main()
