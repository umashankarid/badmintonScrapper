# Local Development Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the whole application run on a developer machine with no real Badminton Sweden credentials and no live external calls, behind a live/dev switch that only exists locally.

**Architecture:** All Badminton Sweden access moves out of `app.py` into a three-module boundary — `bwf_client.py` dispatches per call to either `bwf_live.py` (today's scraping code, moved verbatim) or `bwf_dev.py` (stubs returning the same Python shapes). The current mode is a process global, `"live"` by default and never persisted, read per request so a UI toggle works without a restart. The toggle itself only exists when the environment variable `DEV_TOOLS` is set, which happens only in `run-local.ps1`.

**Tech Stack:** Python 3.10+ (production image is `python:3.10-slim`; local venv is 3.12), Flask 3.1.0, requests 2.32.3, BeautifulSoup 4.12.3, unittest + `unittest.mock`, pytest 7.4.3 as the runner, vanilla JavaScript for the UI bar.

**Spec:** `docs/superpowers/specs/2026-09-09-local-dev-mode-design.md`

## Global Constraints

- **Production behaviour must not change.** `DEV_TOOLS` unset means `get_mode()` returns `"live"` unconditionally and the toggle endpoints return `404`.
- **Live is the default.** The mode global initialises to `"live"` on every boot and is never persisted to disk or database.
- **No database schema changes.** No `ALTER TABLE`, no new tables.
- **`send_email()` is out of scope.** `EMAIL_ENABLED` already covers Brevo; do not add a second mechanism.
- **All fake dates are computed relative to `date.today()`.** Never hardcode a year in `bwf_dev.py`.
- **Every stub return value carries `"_fake": True`.** No live code path ever sets it.
- **Repository convention: tests live at the repository root** as `test_*.py`, not in a `tests/` directory.
- **Do not add tests to `test_badminton.py`.** That file runs on every server boot and blocks startup on failure; new tests go in new files.
- **Follow `CODE_GUIDELINES.md`:** test first, log at INFO for events and ERROR for failures, update `CHANGES.md`, never push without explicit user approval.
- **Test command:** `.venv\Scripts\python.exe -m pytest <file> -v` (PowerShell). The startup gate is `.venv\Scripts\python.exe run_tests.py`.

---

## File Structure

**Created:**

| File | Responsibility |
| --- | --- |
| `bwf_client.py` | Mode state (`get_mode`, `set_mode`, `dev_tools_enabled`) and the dispatcher functions `app.py` imports. Contains no HTTP and no HTML parsing. |
| `bwf_live.py` | Every real Badminton Sweden call, moved verbatim out of `app.py`. The only module in the project that names `tournamentsoftware.com`. |
| `bwf_dev.py` | Personas, fake tournaments and stub implementations. Imports no network library. |
| `static/devbar.js` | Fetches `/api/dev-mode`, renders the mode bar, flips the mode. No-ops when the endpoint 404s. |
| `test_bwf_client.py` | Characterization tests for each extracted function, and dispatcher tests. |
| `test_dev_mode.py` | Mode state, the toggle endpoints, and the three guard tests. |

**Modified:**

| File | Change |
| --- | --- |
| `app.py` | Sixteen functions lose their scraping bodies and call `bwf_client` instead. Two new endpoints. Ends with zero occurrences of `tournamentsoftware.com`. |
| `players_scraper.py` | Its two `requests.get` calls route through `bwf_client`. |
| `templates/*.html` | One `<script src="/static/devbar.js">` line each. |
| `run-local.ps1` | Adds `DEV_TOOLS=1`. |
| `AGENTS.md`, `CHANGES.md` | Documentation. |

**Interface note carried across every task:** `bwf_client` exposes the same function names as `bwf_live` and `bwf_dev`, and simply forwards. Adding a function means adding it in all three.

---

### Task 1: Mode state

**Files:**
- Create: `bwf_client.py`
- Test: `test_dev_mode.py`

**Interfaces:**
- Consumes: nothing
- Produces: `bwf_client.dev_tools_enabled() -> bool`, `bwf_client.get_mode() -> str` (`"live"` or `"dev"`), `bwf_client.set_mode(mode: str) -> str` (returns the mode now in effect; raises `ValueError` on an unknown mode)

- [ ] **Step 1: Write the failing tests**

```python
# test_dev_mode.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwf_client'`

- [ ] **Step 3: Write the minimal implementation**

```python
# bwf_client.py
"""
Boundary for every Badminton Sweden interaction.

app.py talks only to this module. It dispatches each call to bwf_live (real
scraping) or bwf_dev (stubs), depending on the current mode.

Mode rules:
- DEV_TOOLS unset  -> always "live". This is production; the toggle does not exist.
- DEV_TOOLS=1      -> starts "live", switchable at runtime via set_mode().

The mode is deliberately not persisted: every restart returns to live.
"""

import logging
import os

logger = logging.getLogger(__name__)

VALID_MODES = ("live", "dev")

_mode = "live"


def dev_tools_enabled():
    """True when this server is allowed to offer a development mode at all."""
    return os.environ.get("DEV_TOOLS", "").lower() in ("1", "true", "yes")


def get_mode():
    """The mode in effect for this request. Always 'live' in production."""
    if not dev_tools_enabled():
        return "live"
    return _mode


def set_mode(mode):
    """Switch mode. Returns the mode now in effect."""
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown mode {mode!r}, expected one of {VALID_MODES}")
    global _mode
    _mode = mode
    logger.info(f"🔀 BWF mode set to: {mode}")
    return get_mode()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 5: Commit**

```bash
git add bwf_client.py test_dev_mode.py
git commit -m "Feature: Add BWF mode state, live by default and gated on DEV_TOOLS"
```

---

### Task 2: Toggle endpoints

**Files:**
- Modify: `app.py` (add two routes next to the other `/api/` routes, after `get_scheduler_status`)
- Test: `test_dev_mode.py`

**Interfaces:**
- Consumes: `bwf_client.get_mode()`, `bwf_client.set_mode()`, `bwf_client.dev_tools_enabled()`
- Produces: `GET /api/dev-mode` → `{"dev_tools": bool, "mode": str}`; `POST /api/dev-mode` with body `{"mode": "dev"}` → `{"success": true, "mode": "dev"}`. Both return `404` when `DEV_TOOLS` is unset.

- [ ] **Step 1: Write the failing tests**

Append to `test_dev_mode.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py::TestModeEndpoints -v`
Expected: FAIL — the 404 tests pass by accident (no route exists), the rest fail on 404 where 200 was expected.

- [ ] **Step 3: Write the implementation**

Add near the top of `app.py`, with the other imports:

```python
import bwf_client
```

Add after `get_scheduler_status()`:

```python
# ==================== LOCAL DEVELOPMENT MODE ====================

@app.route("/api/dev-mode", methods=["GET"])
def get_dev_mode():
    """Report whether dev tools exist on this server, and the mode in effect."""
    if not bwf_client.dev_tools_enabled():
        return jsonify(success=False, error="Not found"), 404
    return jsonify(dev_tools=True, mode=bwf_client.get_mode())


@app.route("/api/dev-mode", methods=["POST"])
def set_dev_mode():
    """Switch between live and dev. Local servers only."""
    if not bwf_client.dev_tools_enabled():
        return jsonify(success=False, error="Not found"), 404
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401

    mode = (request.json or {}).get("mode", "")
    try:
        active = bwf_client.set_mode(mode)
    except ValueError as e:
        logger.warning(f"⚠️  Rejected dev-mode switch: {e}")
        return jsonify(success=False, error=str(e)), 400

    logger.info(f"🔀 Mode switched to {active} by admin session")
    return jsonify(success=True, mode=active)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 5: Verify the startup gate still passes**

Run: `.venv\Scripts\python.exe run_tests.py`
Expected: `Ran 10 tests` — `OK`

- [ ] **Step 6: Commit**

```bash
git add app.py test_dev_mode.py
git commit -m "Feature: Add /api/dev-mode toggle, 404 when DEV_TOOLS is unset"
```

---

### Task 3: Extract `get_player_license`

This is the smallest extraction and establishes the pattern every later extraction follows: characterization test first, move the body, point the caller at the client.

**Files:**
- Create: `bwf_live.py`
- Modify: `app.py:464-483` (`get_player_license`), `bwf_client.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Consumes: `bwf_client.get_mode()`
- Produces: `bwf_live.get_player_license(player_name: str) -> str` (the licence ID, or `""` when not found or on any error); `bwf_client.get_player_license(player_name)` forwarding to it

- [ ] **Step 1: Write the characterization test**

This pins the behaviour that exists today, before anything moves.

```python
# test_bwf_client.py
"""
Characterization tests for the Badminton Sweden boundary.

These describe what the scraping code does today. They are the safety net for
moving it out of app.py: behaviour must not change during the move.
"""

import unittest
from unittest.mock import MagicMock, patch

import bwf_client


SEARCH_HTML = """
<ul>
  <li class="list__item">
    <a class="media__link" href="/player-profile/ABC-123">
      <span class="nav-link__value">Anna Andersson</span>
    </a>
    <span class="media__title-aside">(SE12345)</span>
    <div class="media__subheading"><span class="nav-link__value">BMK Komet | Stockholm</span></div>
  </li>
</ul>
"""


class TestGetPlayerLicense(unittest.TestCase):
    """Licence lookup by exact name match."""

    def _response(self, html):
        resp = MagicMock()
        resp.text = html
        return resp

    @patch("bwf_live.ext_requests.get")
    def test_returns_license_for_exact_name(self, mock_get):
        mock_get.return_value = self._response(SEARCH_HTML)
        self.assertEqual(bwf_client.get_player_license("Anna Andersson"), "SE12345")

    @patch("bwf_live.ext_requests.get")
    def test_name_match_is_case_insensitive(self, mock_get):
        mock_get.return_value = self._response(SEARCH_HTML)
        self.assertEqual(bwf_client.get_player_license("anna andersson"), "SE12345")

    @patch("bwf_live.ext_requests.get")
    def test_returns_empty_for_unknown_name(self, mock_get):
        mock_get.return_value = self._response(SEARCH_HTML)
        self.assertEqual(bwf_client.get_player_license("Nobody At All"), "")

    @patch("bwf_live.ext_requests.get")
    def test_returns_empty_on_network_error(self, mock_get):
        """Errors are swallowed and reported as 'no licence', as today."""
        mock_get.side_effect = Exception("connection refused")
        self.assertEqual(bwf_client.get_player_license("Anna Andersson"), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwf_live'`

- [ ] **Step 3: Create `bwf_live.py` and move the function**

Create `bwf_live.py`:

```python
"""
Real Badminton Sweden access.

Every function here was moved verbatim from app.py. This is the only module in
the project that names tournamentsoftware.com.
"""

import json
import logging

import requests as ext_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"


def get_player_license(player_name):
    """Look up a player's license ID from Badminton Sweden search."""
    try:
        resp = ext_requests.get(
            f"{BASE_URL}/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": player_name},
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"},
            timeout=5
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("li.list__item"):
            name_el = item.select_one("a.media__link span.nav-link__value")
            if name_el and name_el.get_text(strip=True).lower() == player_name.lower():
                license_el = item.select_one(".media__title-aside")
                if license_el:
                    return license_el.get_text(strip=True).strip("()")
    except Exception:
        pass
    return ""
```

Add to `bwf_client.py`, below the mode functions:

```python
import bwf_dev
import bwf_live


def _backend():
    """The module that services calls right now."""
    return bwf_dev if get_mode() == "dev" else bwf_live


def get_player_license(player_name):
    return _backend().get_player_license(player_name)
```

Create `bwf_dev.py` as a stub file for now so the import resolves:

```python
"""
Fake Badminton Sweden data for local development.

Imports no network library, on purpose: if anything here tries to reach the
internet, that is a bug, and the absence of an import makes it obvious.
"""

import logging

logger = logging.getLogger(__name__)


def get_player_license(player_name):
    raise NotImplementedError("Stub added in Task 12")
```

- [ ] **Step 4: Delete the old function from `app.py` and point callers at the client**

Delete `get_player_license` from `app.py` (lines 464-483). Find its callers:

Run: `grep -n "get_player_license(" app.py`

Replace each call with `bwf_client.get_player_license(...)`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 6: Commit**

```bash
git add bwf_live.py bwf_dev.py bwf_client.py app.py test_bwf_client.py
git commit -m "Refactor: Extract get_player_license behind the BWF client boundary"
```

---

### Task 4: Extract `get_player_ranking`

**Files:**
- Modify: `app.py:485-539`, `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Consumes: the Task 3 boundary
- Produces: `bwf_live.get_player_ranking(player_name: str) -> str`

**Type trap, do not normalise it:** this function returns a **JSON string**, not a dict — `json.dumps({...})` — or `""` when there is no ranking. Callers store it straight into `players.ranking`. Changing the type here breaks `_check_points_too_high()`, which does `json.loads()` on it.

- [ ] **Step 1: Write the characterization test**

Append to `test_bwf_client.py`:

```python
RANKING_HTML = """
<table>
  <tr><th>Category</th><th>Rank</th><th>Points</th></tr>
  <tr><th scope="row">HS</th><td>42</td><td>1500</td></tr>
  <tr><th scope="row">HD</th><td>17</td><td>2100</td></tr>
</table>
"""


class TestGetPlayerRanking(unittest.TestCase):
    """Ranking lookup returns a JSON STRING, not a dict."""

    def _session(self, search_html, ranking_html):
        session = MagicMock()
        search_resp, ranking_resp = MagicMock(), MagicMock()
        search_resp.text, ranking_resp.text = search_html, ranking_html
        session.get.side_effect = [search_resp, ranking_resp]
        return session

    @patch("bwf_live.ext_requests.Session")
    def test_returns_json_string_of_ranking(self, mock_session_cls):
        mock_session_cls.return_value = self._session(SEARCH_HTML, RANKING_HTML)
        result = bwf_client.get_player_ranking("Anna Andersson")
        self.assertIsInstance(result, str)
        self.assertEqual(
            json.loads(result),
            {"HS": {"rank": "42", "points": "1500"},
             "HD": {"rank": "17", "points": "2100"}},
        )

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_string_when_player_not_found(self, mock_session_cls):
        mock_session_cls.return_value = self._session("<ul></ul>", RANKING_HTML)
        self.assertEqual(bwf_client.get_player_ranking("Nobody At All"), "")

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_string_when_no_ranking_table(self, mock_session_cls):
        mock_session_cls.return_value = self._session(SEARCH_HTML, "<div>no table</div>")
        self.assertEqual(bwf_client.get_player_ranking("Anna Andersson"), "")
```

Add `import json` to the imports at the top of `test_bwf_client.py`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestGetPlayerRanking -v`
Expected: FAIL with `AttributeError: module 'bwf_live' has no attribute 'get_player_ranking'`

- [ ] **Step 3: Move the function**

Move the body of `get_player_ranking` from `app.py:485-539` into `bwf_live.py` unchanged, replacing each literal `https://badmintonsweden.tournamentsoftware.com` with the `BASE_URL` constant. Add the forwarder to `bwf_client.py`:

```python
def get_player_ranking(player_name):
    return _backend().get_player_ranking(player_name)
```

Add to `bwf_dev.py`:

```python
def get_player_ranking(player_name):
    raise NotImplementedError("Stub added in Task 12")
```

- [ ] **Step 4: Delete from `app.py` and repoint callers**

Run: `grep -n "get_player_ranking(" app.py`
Replace each call with `bwf_client.get_player_ranking(...)`.

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 6: Commit**

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Extract get_player_ranking behind the BWF client boundary"
```

---

### Task 5: Extract `login` and `verify_credentials`

The largest and riskiest extraction: `bwf_login()` is roughly 240 lines and mixes scraping, session writes and two database writes.

**Files:**
- Modify: `app.py:676-914` (`bwf_login`), `app.py:1317-1368` (`add_admin`), `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces:
  - `bwf_live.login(username, password) -> dict | None` — `None` means the credentials were rejected. On success:
    ```python
    {
        "player_name": str, "license_id": str, "club": str, "gender": str,
        "email": str, "phone": str, "dob": str, "age": str,
        "ranking": dict,          # {"HS": {"rank": "42", "points": "1500"}, ...}
        "profile_url": str,       # "" for club accounts
        "is_club_account": bool,  # True when the login has no player profile
    }
    ```
  - `bwf_live.verify_credentials(username, password) -> bool`

**Split of responsibility — this is the point of the task.** `bwf_live.login()` scrapes and returns the dict. Everything else stays in `app.py`: writing `session[...]`, calling `is_admin_user()`, `update_player_in_db()`, and the `kometPlayers` insert. The client must not touch Flask or the database.

- [ ] **Step 1: Write the characterization tests**

```python
LOGIN_PAGE_HTML = """
<form>
  <input name="__RequestVerificationToken" value="tok123">
  <input name="LogoUrl" value="/logo.png">
  <input name="Login">
</form>
"""

LOGGED_IN_HTML = """
<div class="masthead__user-title">Anna Andersson</div>
<a href="/player-profile/ABC-123">Min profil</a>
"""

ACCOUNT_HTML = """
<dl>
  <dt>Kön:</dt><dd>Kvinna</dd>
  <dt>E-mail:</dt><dd>anna@example.com (Redigera)</dd>
  <dt>Telefon (mobil):</dt><dd>0700000000</dd>
  <dt>Födelsedatum:</dt><dd>2011-05-04 00:00</dd>
</dl>
"""


class TestLogin(unittest.TestCase):
    """Login scrapes a player profile and returns a plain dict."""

    def _session(self, pages):
        session = MagicMock()
        responses = []
        for html in pages:
            resp = MagicMock()
            resp.text = html
            responses.append(resp)
        session.get.side_effect = responses
        session.post.return_value = responses[-1]
        return session

    @patch("bwf_live.ext_requests.Session")
    def test_rejected_credentials_return_none(self, mock_session_cls):
        """Still on the login page (an input named Login) means failure."""
        session = MagicMock()
        resp = MagicMock()
        resp.text = LOGIN_PAGE_HTML
        session.get.return_value = resp
        session.post.return_value = resp
        mock_session_cls.return_value = session
        self.assertIsNone(bwf_client.login("someone", "wrong-password"))

    @patch("bwf_live.ext_requests.Session")
    def test_successful_login_returns_profile_dict(self, mock_session_cls):
        session = MagicMock()
        login_page, logged_in = MagicMock(), MagicMock()
        search, account, ranking = MagicMock(), MagicMock(), MagicMock()
        login_page.text = LOGIN_PAGE_HTML
        logged_in.text = LOGGED_IN_HTML
        search.text = SEARCH_HTML
        account.text = ACCOUNT_HTML
        ranking.text = RANKING_HTML
        session.get.side_effect = [login_page, search, account, ranking]
        session.post.return_value = logged_in
        mock_session_cls.return_value = session

        result = bwf_client.login("anna", "correct-password")

        self.assertEqual(result["player_name"], "Anna Andersson")
        self.assertEqual(result["license_id"], "SE12345")
        self.assertEqual(result["club"], "BMK Komet")
        self.assertEqual(result["gender"], "F")
        self.assertEqual(result["email"], "anna@example.com")
        self.assertEqual(result["dob"], "2011-05-04")
        self.assertFalse(result["is_club_account"])

    @patch("bwf_live.ext_requests.Session")
    def test_verify_credentials_true_on_success(self, mock_session_cls):
        session = MagicMock()
        login_page, logged_in = MagicMock(), MagicMock()
        login_page.text = LOGIN_PAGE_HTML
        logged_in.text = LOGGED_IN_HTML
        session.get.return_value = login_page
        session.post.return_value = logged_in
        mock_session_cls.return_value = session
        self.assertTrue(bwf_client.verify_credentials("anna", "correct-password"))

    @patch("bwf_live.ext_requests.Session")
    def test_verify_credentials_false_on_rejection(self, mock_session_cls):
        session = MagicMock()
        resp = MagicMock()
        resp.text = LOGIN_PAGE_HTML
        session.get.return_value = resp
        session.post.return_value = resp
        mock_session_cls.return_value = session
        self.assertFalse(bwf_client.verify_credentials("anna", "wrong-password"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestLogin -v`
Expected: FAIL with `AttributeError: module 'bwf_live' has no attribute 'login'`

- [ ] **Step 3: Move the scraping into `bwf_live.login()`**

Move `app.py:684-838` (cookiewall accept, token fetch, login POST, profile URL discovery, masthead name, licence search, account settings, ranking) into `bwf_live.login()`. Return the dict described in Interfaces instead of writing to `session`. Preserve exactly:

- the club-account branch: when no `player-profile` link is found and the login is `sbf04959` or `umashankar1985@gmail.com`, return a dict with `is_club_account=True`, `player_name` from `.masthead__user-title` (falling back to the login), and empty strings elsewhere
- when no profile is found and the login is *not* one of those two, return `None`
- the age calculation from `dob`, and every `except Exception: pass` — those swallowed errors are current behaviour and the tests pin them

Add `verify_credentials()`, which performs the same cookiewall-token-POST sequence and returns `soup.find("input", {"name": "Login"}) is None`.

- [ ] **Step 4: Rewrite the two callers in `app.py`**

`bwf_login()` becomes:

```python
@app.route("/api/bwf-login", methods=["POST"])
def bwf_login():
    data = request.json
    login = data.get("login", "")
    password = data.get("password", "")
    if not login or not password:
        return jsonify(success=False, error="Login and password required"), 400

    try:
        profile = bwf_client.login(login, password)
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        return jsonify(success=False, error=f"Connection error: {str(e)}"), 500

    if not profile:
        logger.warning(f"⚠️ Login failed for username: {login}")
        return jsonify(success=False, error="Inloggning misslyckades. Kontrollera att användarnamn och lösenord stämmer med ditt Badminton Sweden-konto.\n\nLogin failed. Please check that your username and password match your Badminton Sweden account."), 401

    session["bwf_player"] = profile["player_name"]
    session["bwf_login"] = login
    session["bwf_license_id"] = profile["license_id"]
    session["bwf_club"] = profile["club"]
    session["bwf_gender"] = profile["gender"]
    session["bwf_email"] = profile["email"]
    session["bwf_phone"] = profile["phone"]
    session["bwf_dob"] = profile["dob"]
    session["bwf_age"] = profile["age"]
    session["bwf_ranking"] = profile["ranking"]
    session["admin"] = is_admin_user(login)

    _persist_login_profile(profile)

    logger.info(f"✅ Login successful: {profile['player_name']}")
    return jsonify(success=True, player_name=profile["player_name"],
                   license_id=profile["license_id"], club=profile["club"],
                   gender=profile["gender"], email=profile["email"],
                   phone=profile["phone"], dob=profile["dob"],
                   age=profile["age"], ranking=profile["ranking"])
```

Move the existing `players.db` and `kometPlayers` writes verbatim into a new helper `_persist_login_profile(profile)` in `app.py`, keeping its `try/except` and warning logs exactly as they are.

In `add_admin()`, replace the whole scraping block (`app.py:1327-1352`) with:

```python
    try:
        if not bwf_client.verify_credentials(username, password):
            return jsonify(success=False, error="Invalid Badminton Sweden credentials"), 401
    except Exception as e:
        return jsonify(success=False, error=f"Connection error: {str(e)}"), 500
```

- [ ] **Step 5: Add the dev placeholders**

```python
# bwf_dev.py
def login(username, password):
    raise NotImplementedError("Stub added in Task 12")


def verify_credentials(username, password):
    raise NotImplementedError("Stub added in Task 12")
```

And the forwarders in `bwf_client.py`:

```python
def login(username, password):
    return _backend().login(username, password)


def verify_credentials(username, password):
    return _backend().verify_credentials(username, password)
```

- [ ] **Step 6: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 7: Manually verify a real login still works**

With the server running in live mode, log in through `/login.html` with real credentials and confirm the player name, club and ranking appear as before. This is the one extraction where a silent behaviour change would be most damaging, and the mocked tests cannot prove the real HTML still parses.

- [ ] **Step 8: Commit**

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Extract login and verify_credentials behind the BWF client"
```

---

### Task 6: Extract player search and details

**Files:**
- Modify: `app.py:4040-4088` (`search_players`), `app.py:4092-4189` (`player_details`), `app.py:3222-3410` (`_register_partner`, the BWF part only), `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces:
  - `bwf_live.search_players(query: str) -> list[dict]` — each `{"name": str, "club": str, "license_id": str, "profile_url": str, "source": "live"}`
  - `bwf_live.get_player_details(profile_url: str) -> dict` — `{"gender": str, "email": str, "phone": str, "ranking": dict}`

**Note:** `search_players()` in `app.py` currently uses a function-local `import requests as req`, a second alias for the same library. The extraction removes it. `app.py` keeps the local-database query and the merge of live results with local ones — only the scraping moves.

- [ ] **Step 1: Write the characterization tests**

```python
class TestSearchPlayers(unittest.TestCase):
    @patch("bwf_live.ext_requests.get")
    def test_parses_search_results(self, mock_get):
        resp = MagicMock()
        resp.text = SEARCH_HTML
        mock_get.return_value = resp
        results = bwf_client.search_players("Andersson")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], {
            "name": "Anna Andersson",
            "club": "BMK Komet",
            "license_id": "SE12345",
            "profile_url": "/player-profile/ABC-123",
            "source": "live",
        })

    @patch("bwf_live.ext_requests.get")
    def test_returns_empty_list_on_error(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        self.assertEqual(bwf_client.search_players("Andersson"), [])


class TestGetPlayerDetails(unittest.TestCase):
    @patch("bwf_live.ext_requests.Session")
    def test_parses_details_and_ranking(self, mock_session_cls):
        session = MagicMock()
        profile, ranking = MagicMock(), MagicMock()
        profile.text = ACCOUNT_HTML
        ranking.text = RANKING_HTML
        session.get.side_effect = [profile, ranking]
        mock_session_cls.return_value = session

        details = bwf_client.get_player_details("/player-profile/ABC-123")

        self.assertEqual(details["email"], "anna@example.com")
        self.assertEqual(details["phone"], "0700000000")
        self.assertEqual(details["ranking"]["HS"]["points"], "1500")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestSearchPlayers test_bwf_client.py::TestGetPlayerDetails -v`
Expected: FAIL with `AttributeError` on `bwf_live.search_players`

- [ ] **Step 3: Move the scraping**

Move the `try` block of `search_players` (`app.py:4053-4085`) into `bwf_live.search_players()`, returning `live_results` and returning `[]` from the `except`. Move the profile and ranking scraping of `player_details` into `bwf_live.get_player_details()`, returning the four-key dict. In `_register_partner`, replace the inline ranking fetch with `bwf_client.get_player_details(partner_profile_url)["ranking"]`.

- [ ] **Step 4: Rewrite the callers**

`search_players()` keeps its local query and merge:

```python
    live_results = bwf_client.search_players(query)
    seen = {r["name"] for r in live_results}
    combined = live_results + [r for r in local_results if r["name"] not in seen]
    conn.close()
    return jsonify(combined[:20])
```

- [ ] **Step 5: Add placeholders in `bwf_dev.py` and forwarders in `bwf_client.py`**

```python
# bwf_client.py
def search_players(query):
    return _backend().search_players(query)


def get_player_details(profile_url):
    return _backend().get_player_details(profile_url)
```

```python
# bwf_dev.py
def search_players(query):
    raise NotImplementedError("Stub added in Task 12")


def get_player_details(profile_url):
    raise NotImplementedError("Stub added in Task 12")
```

- [ ] **Step 6: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 7: Commit**

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Extract player search and details behind the BWF client"
```

---

### Task 7: Extract tournament discovery

**Files:**
- Modify: `app.py:1588-1657` (`search_tournaments_bwf`), `app.py:1659-1742` (`fetch_tournament_info`), `app.py:2052-2382` (`get_all_bwf_tournaments`), `app.py:2589-2770` (`ensure_tournament`), `app.py:5416-5489` (`search_tournaments`), `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces:
  - `bwf_live.search_tournaments(query: str) -> list[dict]` — `{"name", "url", "location", "date_start", "date_end"}`
  - `bwf_live.fetch_tournament_info(url: str) -> dict` — `{"name", "location", "levels": list[str], "registration_opens", "registration_closes", "cancellation_deadline", "competition_start", "competition_end"}`, every date `"YYYY-MM-DD"` or `""`
  - `bwf_live.list_all_tournaments(start_date: str, end_date: str) -> list[dict]` — same keys as `search_tournaments`
  - `bwf_live.get_tournament_events(tournament_id: str) -> dict` — `{"singles_levels": [...], "doubles_levels": [...], "mixed_levels": [...]}`

- [ ] **Step 1: Write the characterization tests**

```python
TOURNAMENT_HTML = """
<div class="media__title"><a href="/tournament/T-1">Vikingaslaget</a></div>
<div class="media__subheading">Sollentuna</div>
<div class="tournament-meta__timeline">
  <ul>
    <li><span class="list__value">Anmälan öppnar</span><time datetime="2026-01-01T00:00:00"></time></li>
    <li><span class="list__value">Anmälan stänger</span><time datetime="2026-02-01T00:00:00"></time></li>
    <li><span class="list__value">Sista återbud</span><time datetime="2026-02-10T00:00:00"></time></li>
    <li><span class="list__value">Tävlingen startar</span><time datetime="2026-03-01T00:00:00"></time></li>
    <li><span class="list__value">Tävlingen slutar</span><time datetime="2026-03-02T00:00:00"></time></li>
  </ul>
</div>
"""

EVENTS_HTML = """
<div>
  <a>HS A</a><a>DS B</a><a>HD A</a><a>DD B</a><a>MD C</a>
</div>
"""


class TestFetchTournamentInfo(unittest.TestCase):
    @patch("bwf_live.ext_requests.Session")
    def test_parses_name_location_and_all_five_dates(self, mock_session_cls):
        session = MagicMock()
        page, events = MagicMock(), MagicMock()
        page.text = TOURNAMENT_HTML
        events.text = EVENTS_HTML
        session.get.side_effect = [page, events]
        mock_session_cls.return_value = session

        info = bwf_client.fetch_tournament_info(
            "https://badmintonsweden.tournamentsoftware.com/tournament/T-1")

        self.assertEqual(info["name"], "Vikingaslaget")
        self.assertEqual(info["registration_opens"], "2026-01-01")
        self.assertEqual(info["registration_closes"], "2026-02-01")
        self.assertEqual(info["cancellation_deadline"], "2026-02-10")
        self.assertEqual(info["competition_start"], "2026-03-01")
        self.assertEqual(info["competition_end"], "2026-03-02")


class TestGetTournamentEvents(unittest.TestCase):
    @patch("bwf_live.ext_requests.Session")
    def test_sorts_events_into_singles_doubles_and_mixed(self, mock_session_cls):
        session = MagicMock()
        events = MagicMock()
        events.text = EVENTS_HTML
        session.get.return_value = events
        mock_session_cls.return_value = session

        result = bwf_client.get_tournament_events("T-1")

        self.assertEqual(sorted(result["singles_levels"]), ["DS B", "HS A"])
        self.assertEqual(sorted(result["doubles_levels"]), ["DD B", "HD A"])
        self.assertEqual(result["mixed_levels"], ["MD C"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestFetchTournamentInfo -v`
Expected: FAIL with `AttributeError` on `bwf_live.fetch_tournament_info`

- [ ] **Step 3: Move the scraping, one function per commit**

Do these as four separate commits, running the suite between each:

1. `fetch_tournament_info` — from `app.py:1669-1740`. `ensure_tournament()` also scrapes the same page (`app.py:2617-2700`); point it at the same client function and delete its duplicate scraping.
2. `get_tournament_events` — the events-page block inside `ensure_tournament` (`app.py:2672-2700`).
3. `search_tournaments` — from `app.py:5431-5487`, used by the results page.
4. `list_all_tournaments` — the calendar scrape in `get_all_bwf_tournaments` (`app.py:2106-2230`). This function also reads the local database and merges; only the scraping moves.

`search_tournaments_bwf` (`app.py:1594-1650`) calls the same `/find/tournament/DoSearch` endpoint as `search_tournaments`. Check whether one client function serves both. If the parsing differs, keep both and name the second `search_tournaments_admin`; do not force a merge during an extraction.

- [ ] **Step 4: Add forwarders and placeholders**

Add all four to `bwf_client.py` following the established pattern, and matching `raise NotImplementedError("Stub added in Task 12")` placeholders to `bwf_dev.py`.

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 6: Commit**

Four commits as described in Step 3, for example:

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Extract fetch_tournament_info behind the BWF client"
```

---

### Task 8: Extract the results endpoints

Four near-identical read-only scrapes. Lower risk than the rest: they feed one page and write nothing.

**Files:**
- Modify: `app.py:5496-5535` (`tournament_medals`), `app.py:5537-5565` (`tournament_player_id`), `app.py:5567-5644` (`tournament_player_results`), `app.py:5646-5700` (`tournament_clubs`), `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces:
  - `bwf_live.get_tournament_medals(tournament_id) -> list[dict]` — `{"name", "event", "placement"}`
  - `bwf_live.get_tournament_clubs(tournament_id) -> list[dict]` — `{"name", "club", "player_id"}`, deduplicated by name
  - `bwf_live.get_tournament_player_id(tournament_id, player_name) -> str` — `""` when not found
  - `bwf_live.get_tournament_player_results(tournament_id, player_id) -> dict` — `{"stats": list, "matches": list}`

- [ ] **Step 1: Write the characterization test**

```python
WINNERS_HTML = """
<table>
  <tr><td>HS A</td></tr>
  <tr><td>Winner</td><td><a>Anna Andersson</a></td></tr>
  <tr><td>Runner-up</td><td><a>Bea Bergstrom</a></td></tr>
</table>
"""


class TestTournamentMedals(unittest.TestCase):
    @patch("bwf_live.ext_requests.Session")
    def test_parses_medals_with_event_and_placement(self, mock_session_cls):
        session = MagicMock()
        resp = MagicMock()
        resp.text = WINNERS_HTML
        session.get.return_value = resp
        mock_session_cls.return_value = session

        medals = bwf_client.get_tournament_medals("T-1")

        self.assertEqual(medals[0], {"name": "Anna Andersson", "event": "HS A", "placement": "Winner"})
        self.assertEqual(medals[1]["placement"], "Runner-up")

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_list_on_error(self, mock_session_cls):
        mock_session_cls.side_effect = Exception("timeout")
        self.assertEqual(bwf_client.get_tournament_medals("T-1"), [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestTournamentMedals -v`
Expected: FAIL with `AttributeError` on `bwf_live.get_tournament_medals`

- [ ] **Step 3: Move all four**

Move each scraping body into `bwf_live.py`, leaving the `jsonify` wrapper and the error responses in `app.py`. Each route becomes roughly:

```python
@app.route("/api/tournament-medals", methods=["GET"])
def tournament_medals():
    tournament_id = request.args.get("id", "").strip()
    if not tournament_id:
        return jsonify(success=False, error="No tournament ID"), 400
    try:
        return jsonify(success=True, medals=bwf_client.get_tournament_medals(tournament_id))
    except Exception as e:
        return jsonify(success=False, error=str(e), medals=[]), 500
```

- [ ] **Step 4: Add forwarders and placeholders**

Four forwarders in `bwf_client.py`, four `NotImplementedError` placeholders in `bwf_dev.py`.

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 6: Commit**

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Extract the four results scrapes behind the BWF client"
```

---

### Task 9: Extract the submit path

**Files:**
- Modify: `app.py:1770-1818` (`submit_tournament`), `bwf_live.py`, `bwf_client.py`, `bwf_dev.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces: `bwf_live.submit_registrations(tournament_name, club_login, club_password) -> dict` — `{"success": bool, "submitted": list, "failed": list, "message": str}`, exactly the shape `bwf_submit.submit_tournament_sync` already returns

- [ ] **Step 1: Write the test**

```python
class TestSubmitRegistrations(unittest.TestCase):
    @patch("bwf_live.submit_tournament_sync")
    def test_forwards_to_playwright_submitter(self, mock_submit):
        mock_submit.return_value = {
            "success": True, "submitted": ["Anna Andersson"],
            "failed": [], "message": "1 registration submitted",
        }
        result = bwf_client.submit_registrations("Vikingaslaget", "sbf04959", "pw")
        self.assertTrue(result["success"])
        mock_submit.assert_called_once()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestSubmitRegistrations -v`
Expected: FAIL with `AttributeError` on `bwf_live.submit_registrations`

- [ ] **Step 3: Implement**

In `bwf_live.py`:

```python
def submit_registrations(tournament_name, club_login, club_password):
    """File the club's entries on Badminton Sweden. Launches a real browser."""
    from bwf_submit import submit_tournament_sync

    return submit_tournament_sync(
        tournament_name=tournament_name,
        club_login=club_login,
        club_password=club_password,
        headless=True,
    )
```

The import stays function-local so that `bwf_live` can be imported without Playwright installed — `app.py` relies on catching `ImportError` to produce its "Playwright is not installed" message.

In `app.py`, replace the `from bwf_submit import submit_tournament_sync` block with `result = bwf_client.submit_registrations(tournament_name, club_login, club_password)`, keeping the surrounding `try`, the `ImportError` branch and the response unchanged.

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 5: Commit**

```bash
git add bwf_live.py bwf_client.py bwf_dev.py app.py test_bwf_client.py
git commit -m "Refactor: Route the Playwright submit through the BWF client"
```

---

### Task 10: Route `players_scraper` through the client

**Files:**
- Modify: `players_scraper.py:44`, `players_scraper.py:76`, `bwf_live.py`, `bwf_client.py`
- Test: `test_bwf_client.py`

**Interfaces:**
- Produces: `bwf_live.get_player_profile_by_license(license_id) -> dict | None` — the parsed profile fields `players_scraper.scrape_player_by_license_id` needs: `{"name", "club", "gender", "email", "phone", "dob", "age", "ranking", "profile_url"}`

**Care required:** `players_scraper` is imported by `app.py` at module scope (`from players_scraper import init_allplayers_table`) and `bwf_client` will import `bwf_live`. Do not create a cycle: `players_scraper` may import `bwf_client`, but `bwf_client` and `bwf_live` must never import `players_scraper`.

- [ ] **Step 1: Write the test**

```python
class TestPlayerProfileByLicense(unittest.TestCase):
    @patch("bwf_live.ext_requests.get")
    def test_returns_none_when_profile_missing(self, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        mock_get.return_value = resp
        self.assertIsNone(bwf_client.get_player_profile_by_license("NOPE"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py::TestPlayerProfileByLicense -v`
Expected: FAIL with `AttributeError` on `bwf_live.get_player_profile_by_license`

- [ ] **Step 3: Move the two requests calls**

Move the profile fetch (`players_scraper.py:44`) and the ranking fetch (`players_scraper.py:76`) into `bwf_live.get_player_profile_by_license()`. `players_scraper` keeps the database write and calls `bwf_client.get_player_profile_by_license(license_id)`.

- [ ] **Step 4: Run the tests, including the existing player storage suite**

Run: `.venv\Scripts\python.exe -m pytest test_bwf_client.py test_dev_mode.py test_player_storage.py -v`
Expected: PASS. `test_player_storage.py` patches `players_scraper.PLAYERS_DB` and must keep passing unchanged.

- [ ] **Step 5: Commit**

```bash
git add bwf_live.py bwf_client.py players_scraper.py test_bwf_client.py
git commit -m "Refactor: Route players_scraper HTTP through the BWF client"
```

---

### Task 11: Fake data

**Files:**
- Modify: `bwf_dev.py`
- Test: `test_dev_mode.py`

**Interfaces:**
- Produces: `bwf_dev.PLAYERS: list[dict]`, `bwf_dev.TOURNAMENTS: list[dict]`, `bwf_dev.relative_date(days: int) -> str`

- [ ] **Step 1: Write the failing tests**

```python
class TestFakeData(unittest.TestCase):
    """Fixtures must exercise the domain rules and must not rot over time."""

    def test_no_hardcoded_years_in_fixture_dates(self):
        """Every date is relative to today, so fixtures never expire."""
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py::TestFakeData -v`
Expected: FAIL with `AttributeError: module 'bwf_dev' has no attribute 'TOURNAMENTS'`

- [ ] **Step 3: Write the fixtures**

Add to `bwf_dev.py`:

```python
from datetime import date, timedelta


def relative_date(days):
    """A date offset from today, as YYYY-MM-DD. Fixtures must never hardcode a year."""
    return (date.today() + timedelta(days=days)).isoformat()


def _birthday(years_ago):
    """A date of birth for someone who is `years_ago` years old today."""
    today = date.today()
    return date(today.year - years_ago, today.month, max(1, today.day - 1)).isoformat()


PLAYERS = [
    {
        "_fake": True, "player_name": "Klubb Kontot", "license_id": "",
        "club": "BMK Komet", "gender": "", "email": "tavlingar@bmkkomet.se",
        "phone": "", "dob": "", "age": "", "ranking": {},
        "profile_url": "", "is_club_account": True,
        "username": "sbf04959", "groups": [],
    },
    {
        "_fake": True, "player_name": "Adam Adult", "license_id": "DEV-0001",
        "club": "BMK Komet", "gender": "M", "email": "adam@example.test",
        "phone": "0700000001", "dob": _birthday(31), "age": "31",
        "ranking": {"HS": {"rank": "120", "points": "1500"},
                    "HD": {"rank": "95", "points": "1600"},
                    "MD": {"rank": "150", "points": "1200"}},
        "profile_url": "/player-profile/DEV-0001", "is_club_account": False,
        "username": "adam", "groups": ["SENIOR"],
    },
    {
        "_fake": True, "player_name": "Elin Elit", "license_id": "DEV-0002",
        "club": "BMK Komet", "gender": "F", "email": "elin@example.test",
        "phone": "0700000002", "dob": _birthday(27), "age": "27",
        "ranking": {"DS": {"rank": "3", "points": "8000"},
                    "DD": {"rank": "5", "points": "7500"}},
        "profile_url": "/player-profile/DEV-0002", "is_club_account": False,
        "username": "elin", "groups": ["SENIOR"],
    },
    {
        "_fake": True, "player_name": "Jonas Junior", "license_id": "DEV-0003",
        "club": "BMK Komet", "gender": "M", "email": "jonas@example.test",
        "phone": "0700000003", "dob": _birthday(15), "age": "15",
        "ranking": {"HS": {"rank": "400", "points": "350"}},
        "profile_url": "/player-profile/DEV-0003", "is_club_account": False,
        "username": "jonas", "groups": ["LEVEL 3-5"],
    },
    {
        "_fake": True, "player_name": "Mini Minior", "license_id": "DEV-0004",
        "club": "BMK Komet", "gender": "F", "email": "mini@example.test",
        "phone": "0700000004", "dob": _birthday(11), "age": "11",
        "ranking": {"DS": {"rank": "900", "points": "50"}},
        "profile_url": "/player-profile/DEV-0004", "is_club_account": False,
        "username": "mini", "groups": ["LEVEL 3-5"],
    },
    {
        "_fake": True, "player_name": "Sara Sexan", "license_id": "DEV-0005",
        "club": "BMK Komet", "gender": "F", "email": "sara@example.test",
        "phone": "0700000005", "dob": _birthday(16), "age": "16",
        "ranking": {"DS": {"rank": "200", "points": "900"},
                    "DD": {"rank": "180", "points": "950"}},
        "profile_url": "/player-profile/DEV-0005", "is_club_account": False,
        "username": "sara", "groups": ["LEVEL_6"],
    },
    {
        "_fake": True, "player_name": "Pia Partner", "license_id": "DEV-0006",
        "club": "Grannklubben", "gender": "F", "email": "pia@example.test",
        "phone": "0700000006", "dob": _birthday(29), "age": "29",
        "ranking": {"DD": {"rank": "300", "points": "800"},
                    "MD": {"rank": "310", "points": "780"}},
        "profile_url": "/player-profile/DEV-0006", "is_club_account": False,
        "username": "pia", "groups": [],
    },
    {
        "_fake": True, "player_name": "Per Partner", "license_id": "DEV-0007",
        "club": "Grannklubben", "gender": "M", "email": "per@example.test",
        "phone": "0700000007", "dob": _birthday(30), "age": "30",
        "ranking": {"HD": {"rank": "290", "points": "820"},
                    "MD": {"rank": "305", "points": "790"}},
        "profile_url": "/player-profile/DEV-0007", "is_club_account": False,
        "username": "per", "groups": [],
    },
]

TOURNAMENTS = [
    {
        "_fake": True, "fixture": "open",
        "name": "Dev Open (FAKE)",
        "url": "https://dev.local/tournament/DEV-T1",
        "location": "Testhallen, Stockholm",
        "date_start": relative_date(30), "date_end": relative_date(31),
        "registration_opens": relative_date(-10),
        "registration_closes": relative_date(14),
        "cancellation_deadline": relative_date(20),
        "competition_start": relative_date(30),
        "competition_end": relative_date(31),
        "levels": ["HS A", "HS B", "DS A", "DS B", "HD A", "DD B", "MD B"],
    },
    {
        "_fake": True, "fixture": "sjt",
        "name": "Dev SJT Cup (FAKE)",
        "url": "https://dev.local/tournament/DEV-T2",
        "location": "Testhallen, Uppsala",
        "date_start": relative_date(45), "date_end": relative_date(46),
        "registration_opens": relative_date(-5),
        "registration_closes": relative_date(21),
        "cancellation_deadline": relative_date(30),
        "competition_start": relative_date(45),
        "competition_end": relative_date(46),
        "levels": ["HS U15", "DS U15", "MJT HS U13", "MJT DS U13"],
    },
    {
        "_fake": True, "fixture": "closed",
        "name": "Dev Past Cup (FAKE)",
        "url": "https://dev.local/tournament/DEV-T3",
        "location": "Testhallen, Göteborg",
        "date_start": relative_date(-30), "date_end": relative_date(-29),
        "registration_opens": relative_date(-60),
        "registration_closes": relative_date(-40),
        "cancellation_deadline": relative_date(-35),
        "competition_start": relative_date(-30),
        "competition_end": relative_date(-29),
        "levels": ["HS C", "DS C"],
    },
    {
        "_fake": True, "fixture": "accommodation",
        "name": "Dev Away Weekend (FAKE)",
        "url": "https://dev.local/tournament/DEV-T4",
        "location": "Testhallen, Malmö",
        "date_start": relative_date(60), "date_end": relative_date(62),
        "registration_opens": relative_date(-2),
        "registration_closes": relative_date(28),
        "cancellation_deadline": relative_date(40),
        "competition_start": relative_date(60),
        "competition_end": relative_date(62),
        "levels": ["HS B", "DS B", "HD B", "DD B", "MD B"],
    },
]
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 5: Commit**

```bash
git add bwf_dev.py test_dev_mode.py
git commit -m "Feature: Add dev-mode personas and tournament fixtures"
```

---

### Task 12: Stub implementations

**Files:**
- Modify: `bwf_dev.py`
- Test: `test_dev_mode.py`

**Interfaces:**
- Produces: every function name defined in `bwf_live`, with matching return types, sourced from `PLAYERS` and `TOURNAMENTS`

**Password rule:** in dev mode any non-empty password is accepted. The username selects the persona, matched against `username` or `license_id`, case-insensitively. An unknown username returns `None`, so the "bad credentials" path stays testable.

- [ ] **Step 1: Write the failing tests**

```python
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
```

Add `import json` to `test_dev_mode.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py::TestStubs -v`
Expected: FAIL with `NotImplementedError: Stub added in Task 12`

- [ ] **Step 3: Replace every placeholder with a real stub**

```python
def _find_player(needle):
    needle = (needle or "").strip().lower()
    if not needle:
        return None
    for p in PLAYERS:
        if needle in (p["username"].lower(), p["license_id"].lower(),
                      p["player_name"].lower()):
            return p
    return None


def login(username, password):
    if not password:
        return None
    player = _find_player(username)
    if not player:
        logger.info(f"🔀 dev login rejected for unknown persona: {username}")
        return None
    logger.info(f"🔀 dev login as {player['player_name']}")
    return dict(player)


def verify_credentials(username, password):
    return login(username, password) is not None


def search_players(query):
    query = (query or "").strip().lower()
    return [
        {"name": p["player_name"], "club": p["club"], "license_id": p["license_id"],
         "profile_url": p["profile_url"], "source": "live", "_fake": True}
        for p in PLAYERS
        if query and query in p["player_name"].lower() and p["license_id"]
    ]


def get_player_license(player_name):
    player = _find_player(player_name)
    return player["license_id"] if player else ""


def get_player_ranking(player_name):
    """Returns a JSON string, matching bwf_live."""
    player = _find_player(player_name)
    if not player or not player["ranking"]:
        return ""
    return json.dumps(player["ranking"])


def get_player_details(profile_url):
    for p in PLAYERS:
        if p["profile_url"] == profile_url:
            return {"gender": p["gender"], "email": p["email"],
                    "phone": p["phone"], "ranking": p["ranking"], "_fake": True}
    return {"gender": "", "email": "", "phone": "", "ranking": {}, "_fake": True}


def get_player_profile_by_license(license_id):
    for p in PLAYERS:
        if p["license_id"] == license_id:
            return {"name": p["player_name"], "club": p["club"], "gender": p["gender"],
                    "email": p["email"], "phone": p["phone"], "dob": p["dob"],
                    "age": p["age"], "ranking": p["ranking"],
                    "profile_url": p["profile_url"], "_fake": True}
    return None


def _tournament_summary(t):
    return {"name": t["name"], "url": t["url"], "location": t["location"],
            "date_start": t["date_start"], "date_end": t["date_end"], "_fake": True}


def search_tournaments(query):
    query = (query or "").strip().lower()
    return [_tournament_summary(t) for t in TOURNAMENTS if query in t["name"].lower()]


def list_all_tournaments(start_date, end_date):
    return [_tournament_summary(t) for t in TOURNAMENTS]


def fetch_tournament_info(url):
    for t in TOURNAMENTS:
        if t["url"] == url:
            return {"name": t["name"], "location": t["location"], "levels": t["levels"],
                    "registration_opens": t["registration_opens"],
                    "registration_closes": t["registration_closes"],
                    "cancellation_deadline": t["cancellation_deadline"],
                    "competition_start": t["competition_start"],
                    "competition_end": t["competition_end"], "_fake": True}
    raise ValueError(f"No dev tournament for {url}. Known: {[t['url'] for t in TOURNAMENTS]}")


def get_tournament_events(tournament_id):
    for t in TOURNAMENTS:
        if tournament_id in t["url"]:
            # An event string may be prefixed, as in "MJT HS U13", so match on
            # any whitespace-separated token rather than only the first one.
            def _has(event, codes):
                return any(token in codes for token in event.split())

            return {
                "singles_levels": [e for e in t["levels"] if _has(e, ("HS", "DS"))],
                "doubles_levels": [e for e in t["levels"] if _has(e, ("HD", "DD"))],
                "mixed_levels": [e for e in t["levels"] if _has(e, ("MD",))],
                "_fake": True,
            }
    return {"singles_levels": [], "doubles_levels": [], "mixed_levels": [], "_fake": True}


def get_tournament_medals(tournament_id):
    return [
        {"name": "Adam Adult", "event": "HS A", "placement": "Winner", "_fake": True},
        {"name": "Elin Elit", "event": "DS A", "placement": "Winner", "_fake": True},
    ]


def get_tournament_clubs(tournament_id):
    return [{"name": p["player_name"], "club": p["club"], "player_id": p["license_id"],
             "_fake": True} for p in PLAYERS if p["license_id"]]


def get_tournament_player_id(tournament_id, player_name):
    player = _find_player(player_name)
    return player["license_id"] if player else ""


def get_tournament_player_results(tournament_id, player_id):
    return {
        "stats": [{"event": "HS A", "won": 2, "lost": 1, "_fake": True}],
        "matches": [{"event": "HS A", "opponent": "Pia Partner",
                     "score": "21-15 21-18", "result": "Won", "_fake": True}],
        "_fake": True,
    }


def submit_registrations(tournament_name, club_login, club_password):
    """Pretend the submission worked. Playwright is never launched."""
    logger.info(f"🔀 dev submit for '{tournament_name}' — nothing was sent to Badminton Sweden")
    return {"success": True, "submitted": [p["player_name"] for p in PLAYERS if p["license_id"]],
            "failed": [], "message": f"DEV MODE: pretended to submit for '{tournament_name}'",
            "_fake": True}
```

Add `import json` to the top of `bwf_dev.py`.

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py test_bwf_client.py -v`
Expected: PASS, and every previously passing test still passes

- [ ] **Step 5: Commit**

```bash
git add bwf_dev.py test_dev_mode.py
git commit -m "Feature: Implement the dev-mode stub backend"
```

---

### Task 13: The mode bar

**Files:**
- Create: `static/devbar.js`
- Modify: every file in `templates/` except `admin.html` (which is a 16-line redirect page — check it before deciding)
- Test: manual, described below

**Interfaces:**
- Consumes: `GET /api/dev-mode`, `POST /api/dev-mode`

- [ ] **Step 1: Write the script**

```javascript
// static/devbar.js
// Shows which backend the app is talking to, and lets a local developer switch.
// In production /api/dev-mode returns 404 and this script does nothing at all.

(async function () {
  let state;
  try {
    const res = await fetch("/api/dev-mode");
    if (!res.ok) return;            // production: no such endpoint
    state = await res.json();
  } catch (e) {
    return;                          // server down or offline: stay invisible
  }
  if (!state.dev_tools) return;

  const bar = document.createElement("div");
  bar.id = "devbar";
  const render = () => {
    const dev = state.mode === "dev";
    bar.style.cssText = [
      "position:sticky", "top:0", "z-index:9999",
      "padding:6px 12px", "font:600 13px system-ui,sans-serif",
      "display:flex", "gap:12px", "align-items:center",
      "color:#fff", `background:${dev ? "#c2410c" : "#15803d"}`,
    ].join(";");
    bar.innerHTML = "";
    const label = document.createElement("span");
    label.textContent = dev
      ? "DEV — fake data, nothing leaves this machine"
      : "LIVE — real Badminton Sweden";
    const button = document.createElement("button");
    button.textContent = dev ? "Switch to LIVE" : "Switch to DEV";
    button.style.cssText = "padding:2px 10px;cursor:pointer;border-radius:3px;border:1px solid #fff;background:transparent;color:#fff;font:inherit";
    button.onclick = async () => {
      button.disabled = true;
      const res = await fetch("/api/dev-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: dev ? "live" : "dev" }),
      });
      const body = await res.json();
      if (!res.ok) {
        alert(body.error || "Could not switch mode. Are you logged in as admin?");
        button.disabled = false;
        return;
      }
      state.mode = body.mode;
      location.reload();
    };
    bar.append(label, button);
  };
  render();
  document.body.prepend(bar);
})();
```

- [ ] **Step 2: Include it in every page**

Add before `</body>` in each template:

```html
<script src="/static/devbar.js"></script>
```

Run `grep -L "devbar.js" templates/*.html` afterwards; it should list only files you deliberately skipped.

- [ ] **Step 3: Mark fake rows**

In `templates/tournament.html`, where search results are rendered, append a marker when the record carries `_fake`:

```javascript
const fakeTag = p._fake ? ' <span style="background:#c2410c;color:#fff;padding:0 5px;border-radius:3px;font-size:0.75em">FAKE</span>' : "";
```

Apply the same to the tournament list in `templates/index.html`.

- [ ] **Step 4: Verify manually**

1. Start with `.\run-local.ps1` (Task 15 adds `DEV_TOOLS`; until then set `$env:DEV_TOOLS="1"` by hand).
2. Load `http://localhost:3002/` — expect a green LIVE bar.
3. Log in as admin, click **Switch to DEV** — expect an orange bar after the reload.
4. Search for a player — expect `Jonas Junior` with a FAKE tag.
5. Stop the server, start it without `DEV_TOOLS`, reload — expect no bar at all.

- [ ] **Step 5: Commit**

```bash
git add static/devbar.js templates/
git commit -m "Feature: Add the live/dev mode bar and fake-data markers"
```

---

### Task 14: Guard tests

The three checks from the spec. These are what stop dev mode quietly leaking.

**Files:**
- Modify: `test_dev_mode.py`

- [ ] **Step 1: Write the guard tests**

```python
class TestGuards(unittest.TestCase):
    """The three properties that make dev mode trustworthy."""

    def test_app_py_contains_no_badminton_sweden_urls(self):
        """The boundary is real: only bwf_live names the site."""
        with open("app.py", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("tournamentsoftware.com", source)

    @patch.dict(os.environ, {"DEV_TOOLS": "1"})
    def test_dev_mode_makes_no_network_calls(self):
        """The real proof: with every HTTP entry point armed to explode, dev mode works."""
        bwf_client.set_mode("dev")
        try:
            def explode(*args, **kwargs):
                raise AssertionError("dev mode attempted a network call")

            with patch("requests.get", explode), patch("requests.post", explode), \
                 patch("requests.Session", explode):
                self.assertIsNotNone(bwf_client.login("adam", "pw"))
                self.assertTrue(bwf_client.search_players("Adam"))
                self.assertTrue(bwf_client.get_player_ranking("Adam Adult"))
                self.assertTrue(bwf_client.fetch_tournament_info(
                    "https://dev.local/tournament/DEV-T1"))
                self.assertTrue(bwf_client.list_all_tournaments("", ""))
                self.assertTrue(bwf_client.get_tournament_medals("DEV-T1"))
                self.assertTrue(bwf_client.submit_registrations("Dev Open (FAKE)", "x", "y")["success"])
        finally:
            bwf_client.set_mode("live")

    @patch.dict(os.environ, {}, clear=True)
    def test_production_cannot_be_switched_into_dev(self):
        """Even a direct set_mode call cannot move production off live."""
        bwf_client._mode = "dev"
        self.assertEqual(bwf_client.get_mode(), "live")
        bwf_client._mode = "live"

    def test_client_and_dev_expose_the_same_names(self):
        """A function added to one backend but not the other fails here, not in production."""
        import bwf_dev
        import bwf_live
        live_names = {n for n in dir(bwf_live)
                      if not n.startswith("_") and callable(getattr(bwf_live, n))}
        dev_names = {n for n in dir(bwf_dev)
                     if not n.startswith("_") and callable(getattr(bwf_dev, n))}
        missing = live_names - dev_names - {"BeautifulSoup", "relative_date"}
        self.assertEqual(missing, set(), f"bwf_dev is missing stubs for: {missing}")
```

- [ ] **Step 2: Run and fix what they catch**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py::TestGuards -v`
Expected: PASS. If `test_app_py_contains_no_badminton_sweden_urls` fails, an extraction was missed — go back and finish it rather than weakening the test.

- [ ] **Step 3: Run the whole suite and the startup gate**

Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py test_bwf_client.py test_player_storage.py test_reminders.py -v`
Run: `.venv\Scripts\python.exe run_tests.py`
Expected: all PASS; the gate reports `Ran 10 tests` — `OK`

- [ ] **Step 4: Commit**

```bash
git add test_dev_mode.py
git commit -m "Test: Add dev-mode leakage and production guards"
```

---

### Task 15: Wire it up and document it

**Files:**
- Modify: `run-local.ps1`, `AGENTS.md`, `CHANGES.md`

- [ ] **Step 1: Enable dev tools locally**

Add to `run-local.ps1`, after the `EMAIL_ENABLED` line:

```powershell
# Offers the live/dev switch in the UI. Never set in production.
$env:DEV_TOOLS = "1"
```

- [ ] **Step 2: Document the boundary in `AGENTS.md`**

Add to the Architecture section, after the module table:

```markdown
**Badminton Sweden access goes through one boundary.** `app.py` never calls the
site directly — it calls `bwf_client`, which dispatches to `bwf_live` (real
scraping) or `bwf_dev` (stubs), depending on the mode. The mode is `"live"`
unless `DEV_TOOLS` is set, which happens only in `run-local.ps1`. A test asserts
that `tournamentsoftware.com` appears nowhere in `app.py`, so new scraping code
belongs in `bwf_live`, with a matching stub in `bwf_dev`.
```

- [ ] **Step 3: Add the `CHANGES.md` entry**

Under `## [Unreleased]`, following the existing format: what was added, the before and after for the extraction, the test counts, and an Impact block noting no production behaviour change, no schema change and no deployment change.

- [ ] **Step 4: Full verification**

Run: `.venv\Scripts\python.exe run_tests.py`
Run: `.venv\Scripts\python.exe -m pytest test_dev_mode.py test_bwf_client.py -v`

Then start the server with `.\run-local.ps1` and walk the whole flow in dev mode: log in as `mini` (the under-13 persona), open the fake SJT tournament, attempt a senior-class registration and confirm the dispens popup appears. This exercises the domain rules end to end with no network access.

- [ ] **Step 5: Commit**

```bash
git add run-local.ps1 AGENTS.md CHANGES.md
git commit -m "Docs: Enable DEV_TOOLS locally and document the BWF boundary"
```

---

## Notes for the implementer

**The riskiest moment is Task 5.** `bwf_login` is 240 lines mixing scraping, session writes and database writes. The mocked tests prove the dict is shaped correctly; they cannot prove real Badminton Sweden HTML still parses. Do the manual login check in Step 7 before moving on.

**Do not tidy while extracting.** Several functions swallow exceptions with bare `except Exception: pass`, and `search_players` imports `requests` twice under different names. Move that behaviour as it is. An extraction that also fixes things cannot be reviewed as an extraction, and the characterization tests will fight you. Note anything you want to fix and raise it afterwards.

**If a function resists extraction** because scraping and database writes are interleaved (`ensure_tournament` is the likely candidate), split it: the client returns parsed data, `app.py` keeps every `sqlite3` call. The client must import neither `flask` nor `sqlite3`.
