"""
Characterization tests for the Badminton Sweden boundary.

These describe what the scraping code does today. They are the safety net for
moving it out of app.py: behaviour must not change during the move.
"""

import json
import unittest
from datetime import date
from unittest.mock import MagicMock, call, patch

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
        mock_get.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": "Anna Andersson"},
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )

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
        session = self._session(SEARCH_HTML, RANKING_HTML)
        mock_session_cls.return_value = session

        result = bwf_client.get_player_ranking("Anna Andersson")

        self.assertIsInstance(result, str)
        self.assertEqual(
            json.loads(result),
            {"HS": {"rank": "42", "points": "1500"},
             "HD": {"rank": "17", "points": "2100"}},
        )

        # Pin request construction for every outgoing call the function makes.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        session.post.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/cookiewall/Save",
            data={
                "ReturnUrl": "/",
                "SettingsOpen": "false",
                "CookieWallCategoryPreferences": "1,2,3",
            },
            allow_redirects=True,
            timeout=5,
        )
        self.assertEqual(
            session.get.call_args_list,
            [
                call(
                    "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
                    params={"Page": 1, "SportID": 2, "Query": "Anna Andersson"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=5,
                ),
                call(
                    "https://badmintonsweden.tournamentsoftware.com/player-profile/ABC-123/ranking",
                    timeout=5,
                ),
            ],
        )

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_string_when_player_not_found(self, mock_session_cls):
        mock_session_cls.return_value = self._session("<ul></ul>", RANKING_HTML)
        self.assertEqual(bwf_client.get_player_ranking("Nobody At All"), "")

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_string_when_no_ranking_table(self, mock_session_cls):
        mock_session_cls.return_value = self._session(SEARCH_HTML, "<div>no table</div>")
        self.assertEqual(bwf_client.get_player_ranking("Anna Andersson"), "")


BASE = "https://badmintonsweden.tournamentsoftware.com"

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

# A logged-in club account: a masthead name but no player-profile link anywhere.
CLUB_HTML = """
<div class="masthead__user-title">BMK Komet</div>
<a href="/tournaments">Tävlingar</a>
"""


class Boom(Exception):
    """Marker for 'the network blew up' in the tests below."""


def _resp(html):
    resp = MagicMock()
    resp.text = html
    return resp


class TestLogin(unittest.TestCase):
    """Login scrapes a player profile and returns a plain dict."""

    @patch("bwf_live.ext_requests.Session")
    def test_rejected_credentials_return_none(self, mock_session_cls):
        """Still on the login page (an input named Login) means failure."""
        session = MagicMock()
        resp = _resp(LOGIN_PAGE_HTML)
        session.get.return_value = resp
        session.post.return_value = resp
        mock_session_cls.return_value = session
        self.assertIsNone(bwf_client.login("someone", "wrong-password"))

    @patch("bwf_live.ext_requests.Session")
    def test_successful_login_returns_profile_dict(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [
            _resp(LOGIN_PAGE_HTML), _resp(SEARCH_HTML), _resp(ACCOUNT_HTML), _resp(RANKING_HTML)
        ]
        session.post.return_value = _resp(LOGGED_IN_HTML)
        mock_session_cls.return_value = session

        result = bwf_client.login("anna", "correct-password")

        self.assertEqual(result["player_name"], "Anna Andersson")
        self.assertEqual(result["license_id"], "SE12345")
        self.assertEqual(result["club"], "BMK Komet")
        self.assertEqual(result["gender"], "F")
        self.assertEqual(result["email"], "anna@example.com")
        self.assertEqual(result["phone"], "0700000000")
        self.assertEqual(result["dob"], "2011-05-04")
        self.assertEqual(result["profile_url"], "/player-profile/ABC-123")
        self.assertFalse(result["is_club_account"])
        self.assertEqual(
            result["ranking"],
            {"HS": {"rank": "42", "points": "1500"},
             "HD": {"rank": "17", "points": "2100"}},
        )
        today = date.today()
        self.assertEqual(
            result["age"],
            str(today.year - 2011 - ((today.month, today.day) < (5, 4))),
        )

        # Pin request construction for every outgoing call the function makes.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        self.assertEqual(
            session.post.call_args_list,
            [
                call(
                    f"{BASE}/cookiewall/Save",
                    data={
                        "ReturnUrl": "/user",
                        "SettingsOpen": "false",
                        "CookieWallCategoryPreferences": "1,2,3",
                    },
                    allow_redirects=True,
                    timeout=10,
                ),
                call(
                    f"{BASE}/user",
                    data={
                        "__RequestVerificationToken": "tok123",
                        "ReturnUrl": "/",
                        "LogoUrl": "/logo.png",
                        "Login": "anna",
                        "Password": "correct-password",
                    },
                    allow_redirects=True,
                    timeout=10,
                ),
            ],
        )
        self.assertEqual(
            session.get.call_args_list,
            [
                call(f"{BASE}/user", timeout=10),
                call(
                    f"{BASE}/find/player/DoSearch",
                    params={"Page": 1, "SportID": 2, "Query": "Andersson"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=10,
                ),
                call(f"{BASE}/user/account-settings/person", timeout=10),
                call(f"{BASE}/player-profile/ABC-123/ranking", timeout=10),
            ],
        )

    @patch("bwf_live.ext_requests.Session")
    def test_club_account_without_profile_returns_placeholder(self, mock_session_cls):
        """The two known club logins are let through with an empty profile."""
        session = MagicMock()
        session.get.side_effect = [_resp(LOGIN_PAGE_HTML), _resp(CLUB_HTML)]
        session.post.return_value = _resp("<div>logged in</div>")
        mock_session_cls.return_value = session

        result = bwf_client.login("sbf04959", "correct-password")

        self.assertTrue(result["is_club_account"])
        self.assertEqual(result["player_name"], "BMK Komet")
        self.assertEqual(result["license_id"], "")
        self.assertEqual(result["club"], "")
        self.assertEqual(result["gender"], "")
        self.assertEqual(result["email"], "")
        self.assertEqual(result["phone"], "")
        self.assertEqual(result["dob"], "")
        self.assertEqual(result["age"], "")
        self.assertEqual(result["profile_url"], "")
        self.assertEqual(result["ranking"], {})

        # The homepage is re-fetched when the POST response carries no profile link.
        self.assertEqual(
            session.get.call_args_list,
            [call(f"{BASE}/user", timeout=10), call(f"{BASE}/", timeout=10)],
        )

    @patch("bwf_live.ext_requests.Session")
    def test_club_account_falls_back_to_the_login_name(self, mock_session_cls):
        """No masthead title, so the login itself is used as the name."""
        session = MagicMock()
        session.get.side_effect = [_resp(LOGIN_PAGE_HTML), _resp("<div>hi</div>")]
        session.post.return_value = _resp("<div>logged in</div>")
        mock_session_cls.return_value = session

        result = bwf_client.login("umashankar1985@gmail.com", "correct-password")

        self.assertEqual(result["player_name"], "umashankar1985@gmail.com")
        self.assertTrue(result["is_club_account"])

    @patch("bwf_live.ext_requests.Session")
    def test_no_profile_for_an_ordinary_login_returns_none(self, mock_session_cls):
        """Credentials accepted but no player profile found: treated as failure."""
        session = MagicMock()
        session.get.side_effect = [_resp(LOGIN_PAGE_HTML), _resp(CLUB_HTML)]
        session.post.return_value = _resp("<div>logged in</div>")
        mock_session_cls.return_value = session
        self.assertIsNone(bwf_client.login("anna", "correct-password"))

    @patch("bwf_live.ext_requests.Session")
    def test_missing_verification_token_raises(self, mock_session_cls):
        """No token means the login page did not load; the caller reports 500."""
        session = MagicMock()
        session.get.return_value = _resp("<div>maintenance</div>")
        mock_session_cls.return_value = session
        with self.assertRaises(RuntimeError):
            bwf_client.login("anna", "correct-password")
        session.post.assert_called_once()  # only the cookiewall POST went out

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        """login() does not swallow transport errors; app.py turns them into a 500."""
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.login("anna", "correct-password")

    @patch("bwf_live.ext_requests.Session")
    def test_account_settings_failure_is_swallowed(self, mock_session_cls):
        """A broken settings page loses the personal fields but keeps the rest."""
        session = MagicMock()
        session.get.side_effect = [
            _resp(LOGIN_PAGE_HTML), _resp(SEARCH_HTML), Boom("settings down"), _resp(RANKING_HTML)
        ]
        session.post.return_value = _resp(LOGGED_IN_HTML)
        mock_session_cls.return_value = session

        result = bwf_client.login("anna", "correct-password")

        self.assertEqual(result["gender"], "")
        self.assertEqual(result["email"], "")
        self.assertEqual(result["phone"], "")
        self.assertEqual(result["dob"], "")
        self.assertEqual(result["age"], "")
        self.assertEqual(result["license_id"], "SE12345")
        self.assertEqual(
            result["ranking"],
            {"HS": {"rank": "42", "points": "1500"},
             "HD": {"rank": "17", "points": "2100"}},
        )

    @patch("bwf_live.ext_requests.Session")
    def test_ranking_failure_is_swallowed(self, mock_session_cls):
        """A broken ranking page leaves ranking empty rather than failing the login."""
        session = MagicMock()
        session.get.side_effect = [
            _resp(LOGIN_PAGE_HTML), _resp(SEARCH_HTML), _resp(ACCOUNT_HTML), Boom("ranking down")
        ]
        session.post.return_value = _resp(LOGGED_IN_HTML)
        mock_session_cls.return_value = session

        result = bwf_client.login("anna", "correct-password")

        self.assertEqual(result["ranking"], {})
        self.assertEqual(result["email"], "anna@example.com")


class TestVerifyCredentials(unittest.TestCase):
    """A yes/no credential check that scrapes nothing else."""

    @patch("bwf_live.ext_requests.Session")
    def test_verify_credentials_true_on_success(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _resp(LOGIN_PAGE_HTML)
        session.post.return_value = _resp(LOGGED_IN_HTML)
        mock_session_cls.return_value = session

        self.assertTrue(bwf_client.verify_credentials("anna", "correct-password"))

        # Pin request construction for every outgoing call the function makes.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        self.assertEqual(
            session.post.call_args_list,
            [
                call(
                    f"{BASE}/cookiewall/Save",
                    data={
                        "ReturnUrl": "/user",
                        "SettingsOpen": "false",
                        "CookieWallCategoryPreferences": "1,2,3",
                    },
                    allow_redirects=True,
                    timeout=10,
                ),
                call(
                    f"{BASE}/user",
                    data={
                        "__RequestVerificationToken": "tok123",
                        "ReturnUrl": "/",
                        "LogoUrl": "/logo.png",
                        "Login": "anna",
                        "Password": "correct-password",
                    },
                    allow_redirects=True,
                    timeout=10,
                ),
            ],
        )
        session.get.assert_called_once_with(f"{BASE}/user", timeout=10)

    @patch("bwf_live.ext_requests.Session")
    def test_verify_credentials_false_on_rejection(self, mock_session_cls):
        session = MagicMock()
        resp = _resp(LOGIN_PAGE_HTML)
        session.get.return_value = resp
        session.post.return_value = resp
        mock_session_cls.return_value = session
        self.assertFalse(bwf_client.verify_credentials("anna", "wrong-password"))

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.verify_credentials("anna", "correct-password")


if __name__ == "__main__":
    unittest.main()
