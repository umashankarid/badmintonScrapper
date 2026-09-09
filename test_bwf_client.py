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

        # Only the login page was fetched: the rejection short-circuits before the
        # profile search, so this fails if the rejection check is ever removed.
        session.get.assert_called_once_with(f"{BASE}/user", timeout=10)

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
    def test_no_profile_for_an_ordinary_login_raises(self, mock_session_cls):
        """Credentials accepted but no player profile: distinct from a bad password."""
        session = MagicMock()
        session.get.side_effect = [_resp(LOGIN_PAGE_HTML), _resp(CLUB_HTML)]
        session.post.return_value = _resp("<div>logged in</div>")
        mock_session_cls.return_value = session
        with self.assertRaises(bwf_client.ProfileNotFound) as caught:
            bwf_client.login("anna", "correct-password")
        self.assertEqual(str(caught.exception),
                         "Login succeeded but could not find player profile")

    @patch("bwf_live.ext_requests.Session")
    def test_missing_verification_token_raises(self, mock_session_cls):
        """No token means the login page did not load; the caller reports 500."""
        session = MagicMock()
        session.get.return_value = _resp("<div>maintenance</div>")
        mock_session_cls.return_value = session
        with self.assertRaises(bwf_client.LoginPageUnavailable):
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

    @patch("bwf_live.ext_requests.Session")
    def test_missing_verification_token_raises(self, mock_session_cls):
        """Shared with login(): no token is 'site broken', not 'wrong password'."""
        session = MagicMock()
        session.get.return_value = _resp("<div>maintenance</div>")
        mock_session_cls.return_value = session
        with self.assertRaises(bwf_client.LoginPageUnavailable):
            bwf_client.verify_credentials("anna", "correct-password")


PLAYER_PROFILE = {
    "player_name": "Anna Andersson", "license_id": "SE12345", "club": "BMK Komet",
    "gender": "F", "email": "anna@example.com", "phone": "0700000000",
    "dob": "2011-05-04", "age": "15",
    "ranking": {"HS": {"rank": "42", "points": "1500"}},
    "profile_url": "/player-profile/ABC-123", "is_club_account": False,
}

CLUB_PROFILE = dict(PLAYER_PROFILE, player_name="BMK Komet", license_id="", club="",
                    gender="", email="", phone="", dob="", age="", ranking={},
                    profile_url="", is_club_account=True)


class TestBwfLoginEndpoint(unittest.TestCase):
    """/api/bwf-login owns the session writes, the DB write and the status codes."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.app = app
        self.client = app.app.test_client()

    def test_missing_credentials_are_rejected(self):
        resp = self.client.post("/api/bwf-login", json={"login": "", "password": ""})
        self.assertEqual(resp.status_code, 400)

    def test_rejected_credentials_return_401(self):
        with patch("app.bwf_client.login", return_value=None):
            resp = self.client.post("/api/bwf-login", json={"login": "a", "password": "b"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Inloggning misslyckades", resp.get_json()["error"])

    def test_missing_profile_is_a_500_not_a_401(self):
        """A real account with no profile must not be told its password is wrong."""
        boom = bwf_client.ProfileNotFound("Login succeeded but could not find player profile")
        with patch("app.bwf_client.login", side_effect=boom):
            resp = self.client.post("/api/bwf-login", json={"login": "a", "password": "b"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"],
                         "Login succeeded but could not find player profile")

    def test_unloadable_login_page_is_a_500(self):
        boom = bwf_client.LoginPageUnavailable("Could not load login page")
        with patch("app.bwf_client.login", side_effect=boom):
            resp = self.client.post("/api/bwf-login", json={"login": "a", "password": "b"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"], "Could not load login page")

    def test_transport_error_is_a_connection_error(self):
        with patch("app.bwf_client.login", side_effect=Boom("connection refused")):
            resp = self.client.post("/api/bwf-login", json={"login": "a", "password": "b"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"], "Connection error: connection refused")

    def test_successful_login_fills_the_session_and_saves_the_player(self):
        with patch("app.bwf_client.login", return_value=PLAYER_PROFILE), \
             patch("app.is_admin_user", return_value=False), \
             patch("app._persist_login_profile") as persist:
            resp = self.client.post("/api/bwf-login", json={"login": "anna", "password": "b"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json(),
            {"success": True, "player_name": "Anna Andersson", "license_id": "SE12345",
             "club": "BMK Komet", "gender": "F", "email": "anna@example.com",
             "phone": "0700000000", "dob": "2011-05-04", "age": "15",
             "ranking": {"HS": {"rank": "42", "points": "1500"}}},
        )
        persist.assert_called_once_with(PLAYER_PROFILE)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["bwf_player"], "Anna Andersson")
            self.assertEqual(sess["bwf_login"], "anna")
            self.assertEqual(sess["bwf_license_id"], "SE12345")
            self.assertEqual(sess["bwf_club"], "BMK Komet")
            self.assertEqual(sess["bwf_gender"], "F")
            self.assertEqual(sess["bwf_email"], "anna@example.com")
            self.assertEqual(sess["bwf_phone"], "0700000000")
            self.assertEqual(sess["bwf_dob"], "2011-05-04")
            self.assertEqual(sess["bwf_age"], "15")
            self.assertEqual(sess["bwf_ranking"], {"HS": {"rank": "42", "points": "1500"}})
            self.assertIs(sess["admin"], False)

    def test_club_account_is_an_admin_without_a_lookup(self):
        """Club logins have always been admins outright; is_admin_user must not decide."""
        with patch("app.bwf_client.login", return_value=CLUB_PROFILE), \
             patch("app.is_admin_user", return_value=False), \
             patch("app._persist_login_profile"):
            resp = self.client.post("/api/bwf-login",
                                    json={"login": "sbf04959", "password": "b"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["ranking"], {})
        with self.client.session_transaction() as sess:
            self.assertIs(sess["admin"], True)
            self.assertEqual(sess["bwf_player"], "BMK Komet")


class TestAddAdminEndpoint(unittest.TestCase):
    """/admin/add-admin verifies against Badminton Sweden before writing admin.db."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def _post(self):
        return self.client.post("/admin/add-admin", json={
            "username": "u", "password": "p", "confirm_password": "admin@2026"})

    def test_invalid_credentials_return_401(self):
        with patch("app.bwf_client.verify_credentials", return_value=False):
            resp = self._post()
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "Invalid Badminton Sweden credentials")

    def test_unloadable_login_page_returns_500(self):
        boom = bwf_client.LoginPageUnavailable("Could not load login page")
        with patch("app.bwf_client.verify_credentials", side_effect=boom):
            resp = self._post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"], "Could not connect to Badminton Sweden")

    def test_transport_error_returns_500(self):
        with patch("app.bwf_client.verify_credentials", side_effect=Boom("refused")):
            resp = self._post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"], "Connection error: refused")

    def test_wrong_confirmation_password_is_rejected(self):
        resp = self.client.post("/admin/add-admin", json={
            "username": "u", "password": "p", "confirm_password": "nope"})
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
