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


class TestSearchPlayers(unittest.TestCase):
    """Live player search: same DoSearch endpoint and parsing as get_player_license."""

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

        # Pin request construction for the one outgoing call.
        mock_get.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": "Andersson"},
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )

    @patch("bwf_live.ext_requests.get")
    def test_returns_empty_list_when_no_results(self, mock_get):
        resp = MagicMock()
        resp.text = "<ul></ul>"
        mock_get.return_value = resp
        self.assertEqual(bwf_client.search_players("Nobody At All"), [])
        mock_get.assert_called_once()

    @patch("bwf_live.ext_requests.get")
    def test_returns_empty_list_on_error(self, mock_get):
        """Errors are swallowed and reported as 'no results', as today."""
        mock_get.side_effect = Exception("timeout")
        self.assertEqual(bwf_client.search_players("Andersson"), [])
        mock_get.assert_called_once()


class TestGetPlayerDetails(unittest.TestCase):
    """Given an already-known profile_url, scrape gender/email/phone/ranking."""

    @patch("bwf_live.ext_requests.Session")
    def test_parses_details_and_ranking(self, mock_session_cls):
        session = MagicMock()
        profile, ranking = MagicMock(), MagicMock()
        profile.text = ACCOUNT_HTML
        ranking.text = RANKING_HTML
        session.get.side_effect = [profile, ranking]
        mock_session_cls.return_value = session

        details = bwf_client.get_player_details("/player-profile/ABC-123")

        self.assertEqual(details, {
            "gender": "F",
            "email": "anna@example.com",
            "phone": "0700000000",
            "ranking": {
                "HS": {"rank": "42", "points": "1500"},
                "HD": {"rank": "17", "points": "2100"},
            },
        })

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
                call("https://badmintonsweden.tournamentsoftware.com/player-profile/ABC-123", timeout=10),
                call("https://badmintonsweden.tournamentsoftware.com/player-profile/ABC-123/ranking", timeout=10),
            ],
        )

    @patch("bwf_live.ext_requests.Session")
    def test_infers_gender_from_events_when_absent_from_profile(self, mock_session_cls):
        """No Kön dt/dd on the profile page: fall back to scanning event links."""
        session = MagicMock()
        profile, ranking = MagicMock(), MagicMock()
        profile.text = "<a>DS B</a>"
        ranking.text = "<div>no table</div>"
        session.get.side_effect = [profile, ranking]
        mock_session_cls.return_value = session

        details = bwf_client.get_player_details("/player-profile/ABC-123")
        self.assertEqual(details["gender"], "F")
        self.assertEqual(details["ranking"], {})

    @patch("bwf_live.ext_requests.Session")
    def test_ranking_failure_is_swallowed(self, mock_session_cls):
        """A broken ranking page leaves ranking empty rather than raising."""
        session = MagicMock()
        profile = MagicMock()
        profile.text = ACCOUNT_HTML
        session.get.side_effect = [profile, Boom("ranking down")]
        mock_session_cls.return_value = session

        details = bwf_client.get_player_details("/player-profile/ABC-123")
        self.assertEqual(details["ranking"], {})
        self.assertEqual(details["email"], "anna@example.com")

    @patch("bwf_live.ext_requests.Session")
    def test_profile_fetch_failure_propagates(self, mock_session_cls):
        """The profile fetch has no try/except of its own (unlike the ranking fetch):
        a failure bubbles up so app.py's outer handler can turn it into a 500."""
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session

        with self.assertRaises(Boom):
            bwf_client.get_player_details("/player-profile/ABC-123")


class TestGetPlayerRankingByProfile(unittest.TestCase):
    """Ranking-only fetch used by _register_partner — cookiewall + ranking page,
    no profile-page GET (that distinction is the point: get_player_details fetches
    an extra page this function must not)."""

    @patch("bwf_live.ext_requests.Session")
    def test_parses_ranking_table(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _resp(RANKING_HTML)
        mock_session_cls.return_value = session

        result = bwf_client.get_player_ranking_by_profile("/player-profile/ABC-123")

        self.assertEqual(result, {
            "HS": {"rank": "42", "points": "1500"},
            "HD": {"rank": "17", "points": "2100"},
        })

        # Pin request construction: exactly one GET, the ranking page — no profile-page fetch.
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
        session.get.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/player-profile/ABC-123/ranking",
            timeout=10,
        )

    @patch("bwf_live.ext_requests.Session")
    def test_returns_empty_dict_when_no_table(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _resp("<div>no table</div>")
        mock_session_cls.return_value = session
        self.assertEqual(bwf_client.get_player_ranking_by_profile("/player-profile/ABC-123"), {})

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        """No try/except of its own: _register_partner's own try/except is what
        catches this, exactly as the pre-Task-6 inline code did."""
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.get_player_ranking_by_profile("/player-profile/ABC-123")


class TestRegisterPartnerRankingSource(unittest.TestCase):
    """Pins which client function _register_partner's ranking fetch calls.

    Fix round 1 overturned Task 6's original choice of get_player_details:
    routing through it added a profile-page GET and a new failure mode that
    did not exist before Task 6. This is the one guard against a silent
    revert back to it — none of the boundary-function tests above would
    catch that, since they never touch _register_partner.
    """

    def test_uses_the_narrow_ranking_function_not_get_player_details(self):
        import app
        with patch("app.bwf_client.get_player_ranking_by_profile",
                   return_value={"HS": {"rank": "1", "points": "999"}}) as narrow, \
             patch("app.bwf_client.get_player_details") as wide, \
             patch("sqlite3.connect"):
            app._register_partner("Test Cup", "TEST-ROUTING-ONLY", "Smoke Test",
                                   partner_profile_url="/player-profile/XYZ")

        narrow.assert_called_once_with("/player-profile/XYZ")
        wide.assert_not_called()


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


class TestPlayerDetailsEndpoint(unittest.TestCase):
    """/api/player-details: pins which path owns the cookiewall session.

    Regression coverage for fix round 1: the direct-profile_url path (the
    common one — search results already carry profile_url) must create no
    local ext_requests.Session at all, since bwf_client.get_player_details
    makes its own. Only the by-name path still needs app.py's own session,
    to resolve profile_url before delegating.
    """

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def test_direct_profile_url_creates_no_local_session(self):
        details = {"gender": "F", "email": "a@example.com", "phone": "070",
                   "ranking": {}}
        with patch("app.bwf_client.get_player_details", return_value=details) as mocked, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self.client.get("/api/player-details?profile_url=/player-profile/ABC-123")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"success": True, **details})
        mocked.assert_called_once_with("/player-profile/ABC-123")
        # The one place a second cookiewall POST used to sneak in.
        mock_session_cls.assert_not_called()

    def test_by_name_path_resolves_profile_url_then_delegates(self):
        session = MagicMock()
        session.get.return_value = _resp(SEARCH_HTML)
        details = {"gender": "F", "email": "anna@example.com", "phone": "0700000000",
                   "ranking": {"HS": {"rank": "42", "points": "1500"}}}
        with patch("app.ext_requests.Session", return_value=session) as mock_session_cls, \
             patch("app.bwf_client.get_player_details", return_value=details) as mocked:
            resp = self.client.get("/api/player-details?name=Anna+Andersson")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"success": True, **details})

        # Exactly one local session, one cookiewall POST, one DoSearch GET.
        mock_session_cls.assert_called_once()
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
        session.get.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": "Anna Andersson"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=5,
        )
        mocked.assert_called_once_with("/player-profile/ABC-123")


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

EVENTS_URL = "https://badmintonsweden.tournamentsoftware.com/sport/events.aspx?id=T-1"
COOKIEWALL_URL = "https://badmintonsweden.tournamentsoftware.com/cookiewall/Save"
COOKIEWALL_DATA = {
    "ReturnUrl": "/",
    "SettingsOpen": "false",
    "CookieWallCategoryPreferences": "1,2,3",
}


class TestGetTournamentEvents(unittest.TestCase):
    """The events page, in the two shapes app.py has always derived from it."""

    @patch("bwf_live.ext_requests.Session")
    def test_sorts_events_into_singles_doubles_and_mixed(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(EVENTS_HTML)]
        mock_session_cls.return_value = session

        result = bwf_client.get_tournament_events("T-1")

        self.assertEqual(sorted(result["singles_levels"]), ["DS B", "HS A"])
        self.assertEqual(sorted(result["doubles_levels"]), ["DD B", "HD A"])
        self.assertEqual(result["mixed_levels"], ["MD C"])
        # The other shape: the bare level of each class, as /admin/fetch-tournament-info shows.
        self.assertEqual(result["levels"], ["A", "B", "C"])

        # Pin request construction for every outgoing call.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        session.post.assert_called_once_with(
            COOKIEWALL_URL, data=COOKIEWALL_DATA, allow_redirects=True, timeout=5)
        session.get.assert_called_once_with(EVENTS_URL, timeout=10)

    @patch("bwf_live.ext_requests.Session")
    def test_ignores_links_that_are_not_event_classes(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(
            "<div><a>Hem</a><a></a>"
            "<a>PS A</a>"
            "<a>HS A very long class name padded out past the fifty character limit</a>"
            "<a>HD</a></div>")]
        mock_session_cls.return_value = session

        result = bwf_client.get_tournament_events("T-1")

        # "PS A" matches a category code but no *_levels prefix; the long one and
        # the bare "HD" contribute no level.
        self.assertEqual(result["singles_levels"], [])
        self.assertEqual(result["doubles_levels"], ["HD"])
        self.assertEqual(result["mixed_levels"], [])
        self.assertEqual(result["levels"], ["A"])

    def test_reuses_a_supplied_session_without_a_second_cookiewall(self):
        """fetch_tournament_info passes its own session; that must cost no extra request."""
        import bwf_live
        session = MagicMock()
        session.get.side_effect = [_resp(EVENTS_HTML)]

        with patch("bwf_live.ext_requests.Session") as mock_session_cls:
            result = bwf_live.get_tournament_events("T-1", session=session)

        self.assertEqual(result["mixed_levels"], ["MD C"])
        mock_session_cls.assert_not_called()
        session.post.assert_not_called()
        session.headers.update.assert_not_called()
        session.get.assert_called_once_with(EVENTS_URL, timeout=10)

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.get_tournament_events("T-1")



TOURNAMENT_URL = "https://badmintonsweden.tournamentsoftware.com/tournament/T-1"

TOURNAMENT_INFO = {
    "name": "Vikingaslaget",
    "location": "Sollentuna",
    "levels": ["A", "B", "C"],
    "singles_levels": ["DS B", "HS A"],
    "doubles_levels": ["DD B", "HD A"],
    "mixed_levels": ["MD C"],
    "registration_opens": "2026-01-01",
    "registration_closes": "2026-02-01",
    "cancellation_deadline": "2026-02-10",
    "competition_start": "2026-03-01",
    "competition_end": "2026-03-02",
}


class TestFetchTournamentInfo(unittest.TestCase):
    """The tournament page plus its events page, on one session."""

    @patch("bwf_live.ext_requests.Session")
    def test_parses_name_location_and_all_five_dates(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(TOURNAMENT_HTML), _resp(EVENTS_HTML)]
        mock_session_cls.return_value = session

        info = bwf_client.fetch_tournament_info(TOURNAMENT_URL)

        self.assertEqual(info, TOURNAMENT_INFO)

        # Pin request construction: one cookiewall POST, two GETs, no more.
        mock_session_cls.assert_called_once_with()
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        session.post.assert_called_once_with(
            COOKIEWALL_URL, data=COOKIEWALL_DATA, allow_redirects=True, timeout=5)
        self.assertEqual(
            session.get.call_args_list,
            [call(TOURNAMENT_URL, timeout=10), call(EVENTS_URL, timeout=10)],
        )

    @patch("bwf_live.ext_requests.Session")
    def test_falls_back_to_the_title_without_a_link(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [
            _resp('<div class="media__title">Vikingaslaget</div>'), _resp(EVENTS_HTML)]
        mock_session_cls.return_value = session
        self.assertEqual(bwf_client.fetch_tournament_info(TOURNAMENT_URL)["name"], "Vikingaslaget")

    @patch("bwf_live.ext_requests.Session")
    def test_missing_timeline_leaves_every_date_empty(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp("<div>nothing here</div>"), _resp(EVENTS_HTML)]
        mock_session_cls.return_value = session

        info = bwf_client.fetch_tournament_info(TOURNAMENT_URL)

        self.assertEqual(info["name"], "")
        self.assertEqual(info["location"], "")
        for field in ("registration_opens", "registration_closes", "cancellation_deadline",
                      "competition_start", "competition_end"):
            self.assertEqual(info[field], "")

    @patch("bwf_live.ext_requests.Session")
    def test_url_without_a_tournament_id_never_asks_for_events(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(TOURNAMENT_HTML)]
        mock_session_cls.return_value = session

        info = bwf_client.fetch_tournament_info("https://badmintonsweden.tournamentsoftware.com/find")

        self.assertEqual(info["levels"], [])
        self.assertEqual(info["singles_levels"], [])
        session.get.assert_called_once_with(
            "https://badmintonsweden.tournamentsoftware.com/find", timeout=10)

    @patch("bwf_live.ext_requests.Session")
    def test_tournament_page_error_propagates(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.fetch_tournament_info(TOURNAMENT_URL)

    @patch("bwf_live.ext_requests.Session")
    def test_events_page_error_fails_the_whole_call(self, mock_session_cls):
        """/admin/fetch-tournament-info has always turned this into its 500."""
        session = MagicMock()
        session.get.side_effect = [_resp(TOURNAMENT_HTML), Boom("events timed out")]
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.fetch_tournament_info(TOURNAMENT_URL)
        self.assertEqual(session.get.call_count, 2)


class TestFetchTournamentDetails(unittest.TestCase):
    """Same scrape, but tolerant of a missing events page.

    ensure_tournament and the calendar refresh have always stored a tournament
    with empty categories when the events page failed, rather than failing.
    """

    @patch("bwf_live.ext_requests.Session")
    def test_success_matches_fetch_tournament_info(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(TOURNAMENT_HTML), _resp(EVENTS_HTML)]
        mock_session_cls.return_value = session

        self.assertEqual(bwf_client.fetch_tournament_details(TOURNAMENT_URL), TOURNAMENT_INFO)
        self.assertEqual(session.get.call_count, 2)

    @patch("bwf_live.ext_requests.Session")
    def test_events_page_error_only_empties_the_event_lists(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp(TOURNAMENT_HTML), Boom("events timed out")]
        mock_session_cls.return_value = session

        info = bwf_client.fetch_tournament_details(TOURNAMENT_URL)

        self.assertEqual(info["name"], "Vikingaslaget")
        self.assertEqual(info["competition_start"], "2026-03-01")
        self.assertEqual(info["levels"], [])
        self.assertEqual(info["singles_levels"], [])
        self.assertEqual(info["doubles_levels"], [])
        self.assertEqual(info["mixed_levels"], [])
        self.assertEqual(session.get.call_count, 2)

    @patch("bwf_live.ext_requests.Session")
    def test_tournament_page_error_still_propagates(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.fetch_tournament_details(TOURNAMENT_URL)


class TestFetchTournamentInfoEndpoint(unittest.TestCase):
    """/admin/fetch-tournament-info: delegates, and owns no session of its own."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = True

    def _post(self):
        return self.client.post("/admin/fetch-tournament-info", json={"url": TOURNAMENT_URL})

    def test_response_shape_is_unchanged(self):
        with patch("app.bwf_client.fetch_tournament_info", return_value=TOURNAMENT_INFO) as mocked, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self._post()

        self.assertEqual(resp.status_code, 200)
        # location and the grouped class names are not part of this response.
        self.assertEqual(resp.get_json(), {
            "success": True,
            "name": "Vikingaslaget",
            "levels": ["A", "B", "C"],
            "registration_opens": "2026-01-01",
            "registration_closes": "2026-02-01",
            "cancellation_deadline": "2026-02-10",
            "competition_start": "2026-03-01",
            "competition_end": "2026-03-02",
        })
        mocked.assert_called_once_with(TOURNAMENT_URL)
        mock_session_cls.assert_not_called()

    def test_scrape_failure_is_a_500(self):
        with patch("app.bwf_client.fetch_tournament_info", side_effect=Boom("events timed out")):
            resp = self._post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json(), {"success": False, "error": "events timed out"})

    def test_unauthenticated_request_never_scrapes(self):
        import app
        client = app.app.test_client()
        with patch("app.bwf_client.fetch_tournament_info") as mocked:
            resp = client.post("/admin/fetch-tournament-info", json={"url": TOURNAMENT_URL})
        self.assertEqual(resp.status_code, 401)
        mocked.assert_not_called()


class TestEnsureTournamentEndpoint(unittest.TestCase):
    """/api/ensure-tournament: the client parses, app.py owns every sqlite3 call."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def _db(self, existing_row):
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchone.return_value = existing_row
        return conn, cur

    def test_new_tournament_is_scraped_once_and_written_to_the_db(self):
        conn, cur = self._db(None)
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.fetch_tournament_details",
                   return_value=TOURNAMENT_INFO) as mocked, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self.client.post("/api/ensure-tournament", json={"url": TOURNAMENT_URL})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {
            "success": True, "tournament_id": "Vikingaslaget",
            "db": "Vikingaslaget", "created": True})
        mocked.assert_called_once_with(TOURNAMENT_URL)
        mock_session_cls.assert_not_called()

        sql, params = cur.execute.call_args_list[-1][0]
        self.assertIn("INSERT INTO tournaments", sql)
        self.assertEqual(params, (
            TOURNAMENT_URL, "Vikingaslaget", "Sollentuna",
            "2026-03-01", "2026-03-02",
            "2026-01-01", "2026-02-01", "2026-02-10", "2026-03-01", "2026-03-02",
            json.dumps({
                "singles_levels": ["DS B", "HS A"],
                "doubles_levels": ["DD B", "HD A"],
                "mixed_levels": ["MD C"],
                "doubles_partner": ["Partner A", "Partner B", "Partner C"],
                "mixed_partner": ["Partner A", "Partner B", "Partner C"],
            }),
            1,
        ))

    def test_known_tournament_is_never_scraped(self):
        conn, cur = self._db(("Vikingaslaget",))
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.fetch_tournament_details") as mocked:
            resp = self.client.post("/api/ensure-tournament", json={"url": TOURNAMENT_URL})

        self.assertEqual(resp.get_json(), {
            "success": True, "tournament_id": "Vikingaslaget",
            "db": "Vikingaslaget", "created": False})
        mocked.assert_not_called()

    def test_a_tournament_with_no_events_is_still_stored(self):
        """The client swallows an events failure, so this row still gets written."""
        conn, cur = self._db(None)
        no_events = dict(TOURNAMENT_INFO, levels=[], singles_levels=[],
                         doubles_levels=[], mixed_levels=[])
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.fetch_tournament_details", return_value=no_events):
            resp = self.client.post("/api/ensure-tournament", json={"url": TOURNAMENT_URL})

        self.assertEqual(resp.status_code, 200)
        params = cur.execute.call_args_list[-1][0][1]
        self.assertEqual(json.loads(params[10]), {
            "singles_levels": [], "doubles_levels": [], "mixed_levels": [],
            "doubles_partner": [], "mixed_partner": []})

    def test_scrape_failure_is_a_500(self):
        conn, cur = self._db(None)
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.fetch_tournament_details", side_effect=Boom("refused")):
            resp = self.client.post("/api/ensure-tournament", json={"url": TOURNAMENT_URL})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json(), {"success": False, "error": "refused"})



FIND_PAGE_HTML = """
<form id="form_globalsearch">
  <input name="__RequestVerificationToken" value="tok-123" />
  <input name="TournamentExtendedFilter.StatusFilterID" value="4" />
  <input value="ignored-because-it-has-no-name" />
</form>
"""

TOURNAMENT_RESULTS_HTML = """
<ul>
  <li class="list__item">
    <a class="media__link" href="/tournament.aspx?id=AB12-34CD">Vikingaslaget</a>
    <div class="media__subheading"><span class="nav-link__value">Sollentuna</span></div>
    <time datetime="2026-03-01T00:00:00"></time>
    <time datetime="2026-03-02T00:00:00"></time>
    <span class="media__status">Online-anmalan oppen</span>
  </li>
  <li class="list__item"><span>no link at all</span></li>
</ul>
"""

FIND_URL = "https://badmintonsweden.tournamentsoftware.com/find"
DOSEARCH_URL = "https://badmintonsweden.tournamentsoftware.com/find/tournament/DoSearch"


class TestSearchTournaments(unittest.TestCase):
    """The results page search: a find page for the form, then DoSearch."""

    def _session(self):
        session = MagicMock()
        session.get.side_effect = [_resp(FIND_PAGE_HTML)]
        session.post.side_effect = [MagicMock(), _resp(TOURNAMENT_RESULTS_HTML)]
        return session

    @patch("bwf_live.ext_requests.Session")
    def test_parses_id_dates_and_status(self, mock_session_cls):
        session = self._session()
        mock_session_cls.return_value = session

        results = bwf_client.search_tournaments("2026-03-01", "2026-03-31", "2")

        self.assertEqual(results, [{
            "id": "AB12-34CD",
            "name": "Vikingaslaget",
            "location": "Sollentuna",
            "date_start": "2026-03-01",
            "date_end": "2026-03-02",
            "status": "Online-anmalan oppen",
        }])

        # Pin request construction for all three calls.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        session.get.assert_called_once_with(
            FIND_URL + "?DateFilterType=0&StartDate=2026-03-01T00:00&EndDate=2026-03-31T00:00"
                       "&Distance=10&page=1&SportID=2&StatusFilterID=2",
            timeout=10)
        self.assertEqual(session.post.call_args_list, [
            call(COOKIEWALL_URL, data=COOKIEWALL_DATA, allow_redirects=True, timeout=5),
            call(DOSEARCH_URL,
                 data={"__RequestVerificationToken": "tok-123",
                       "TournamentExtendedFilter.StatusFilterID": "2"},
                 headers={"X-Requested-With": "XMLHttpRequest"},
                 timeout=10),
        ])

    @patch("bwf_live.ext_requests.Session")
    def test_blank_dates_and_status_are_left_out_of_the_query(self, mock_session_cls):
        session = self._session()
        mock_session_cls.return_value = session

        bwf_client.search_tournaments("", "", "")

        session.get.assert_called_once_with(
            FIND_URL + "?DateFilterType=0&StartDate=&EndDate=&Distance=10&page=1&SportID=2",
            timeout=10)
        # Without a status the form's own value is posted back untouched.
        self.assertEqual(
            session.post.call_args_list[1][1]["data"],
            {"__RequestVerificationToken": "tok-123",
             "TournamentExtendedFilter.StatusFilterID": "4"})

    @patch("bwf_live.ext_requests.Session")
    def test_missing_form_posts_only_the_status(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp("<div>no search form</div>")]
        session.post.side_effect = [MagicMock(), _resp(TOURNAMENT_RESULTS_HTML)]
        mock_session_cls.return_value = session

        results = bwf_client.search_tournaments("2026-03-01", "", "3")

        self.assertEqual(len(results), 1)
        self.assertEqual(
            session.post.call_args_list[1][1]["data"],
            {"TournamentExtendedFilter.StatusFilterID": "3"})

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.search_tournaments("2026-03-01", "2026-03-31", "2")


class TestSearchTournamentsEndpoint(unittest.TestCase):
    """/api/search-tournaments passes the query through and owns no session."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def test_query_arguments_are_forwarded(self):
        found = [{"id": "T-1", "name": "Vikingaslaget", "location": "Sollentuna",
                  "date_start": "2026-03-01", "date_end": "2026-03-02", "status": "Open"}]
        with patch("app.bwf_client.search_tournaments", return_value=found) as mocked, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self.client.get("/api/search-tournaments?start=2026-03-01&end=2026-03-31&status=2")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"success": True, "tournaments": found})
        mocked.assert_called_once_with("2026-03-01", "2026-03-31", "2")
        mock_session_cls.assert_not_called()

    def test_missing_arguments_become_empty_strings(self):
        with patch("app.bwf_client.search_tournaments", return_value=[]) as mocked:
            self.client.get("/api/search-tournaments")
        mocked.assert_called_once_with("", "", "")

    def test_scrape_failure_is_a_500_with_an_empty_list(self):
        with patch("app.bwf_client.search_tournaments", side_effect=Boom("refused")):
            resp = self.client.get("/api/search-tournaments")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json(),
                         {"success": False, "error": "refused", "tournaments": []})



CALENDAR_RESULTS_HTML = """
<ul>
  <li class="list__item">
    <a class="media__link" href="/tournament.aspx?id=AB12-34CD">Vikingaslaget</a>
    <div class="media__subheading"><span class="nav-link__value">Sollentuna</span></div>
    <time datetime="2026-03-01T00:00:00"></time>
    <time datetime="2026-03-02T00:00:00"></time>
  </li>
  <li class="list__item">
    <a class="media__link" href="/nothing-that-looks-like-an-id">Okand tavling</a>
  </li>
  <li class="list__item"><span>no link at all</span></li>
</ul>
"""


class TestListAllTournaments(unittest.TestCase):
    """The calendar scrape behind both /admin/search-tournaments and the refresh."""

    def _session(self):
        session = MagicMock()
        session.get.side_effect = [_resp(FIND_PAGE_HTML)]
        session.post.side_effect = [MagicMock(), _resp(CALENDAR_RESULTS_HTML)]
        return session

    @patch("bwf_live.ext_requests.Session")
    def test_builds_a_tournament_url_from_the_id_in_the_href(self, mock_session_cls):
        session = self._session()
        mock_session_cls.return_value = session

        results = bwf_client.list_all_tournaments("2026-03-01T00:00", "2026-05-30T00:00")

        self.assertEqual(results, [
            {"name": "Vikingaslaget",
             "url": "https://badmintonsweden.tournamentsoftware.com/tournament/AB12-34CD",
             "location": "Sollentuna",
             "date_start": "2026-03-01",
             "date_end": "2026-03-02"},
            {"name": "Okand tavling", "url": "", "location": "",
             "date_start": "", "date_end": ""},
        ])

        # Pin request construction for all three calls.
        session.headers.update.assert_called_once_with({"User-Agent": "Mozilla/5.0"})
        session.get.assert_called_once_with(
            FIND_URL + "?StatusFilterID=2&DateFilterType=0&StartDate=2026-03-01T00:00"
                       "&EndDate=2026-05-30T00:00&Distance=10&page=1&SportID=2",
            timeout=10)
        self.assertEqual(session.post.call_args_list, [
            call(COOKIEWALL_URL, data=COOKIEWALL_DATA, allow_redirects=True, timeout=5),
            call(DOSEARCH_URL,
                 data={"__RequestVerificationToken": "tok-123",
                       "TournamentExtendedFilter.StatusFilterID": "2"},
                 headers={"X-Requested-With": "XMLHttpRequest"},
                 timeout=10),
        ])

    @patch("bwf_live.ext_requests.Session")
    def test_missing_form_still_forces_the_open_registration_filter(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = [_resp("<div>no search form</div>")]
        session.post.side_effect = [MagicMock(), _resp(CALENDAR_RESULTS_HTML)]
        mock_session_cls.return_value = session

        bwf_client.list_all_tournaments("2026-03-01T00:00", "2026-05-30T00:00")

        self.assertEqual(
            session.post.call_args_list[1][1]["data"],
            {"TournamentExtendedFilter.StatusFilterID": "2"})

    @patch("bwf_live.ext_requests.Session")
    def test_network_error_propagates_to_the_caller(self, mock_session_cls):
        session = MagicMock()
        session.get.side_effect = Boom("connection refused")
        mock_session_cls.return_value = session
        with self.assertRaises(Boom):
            bwf_client.list_all_tournaments("2026-03-01T00:00", "2026-05-30T00:00")


class TestSearchTournamentsBwfEndpoint(unittest.TestCase):
    """/admin/search-tournaments: a 90-day window, and no session of its own."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = True

    def test_asks_for_the_next_ninety_days(self):
        found = [{"name": "Vikingaslaget", "url": "u", "location": "Sollentuna",
                  "date_start": "2026-03-01", "date_end": "2026-03-02"}]
        with patch("app.bwf_client.list_all_tournaments", return_value=found) as mocked, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self.client.get("/admin/search-tournaments")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"success": True, "tournaments": found})
        mock_session_cls.assert_not_called()

        start, end = mocked.call_args[0]
        self.assertRegex(start, r"^\d{4}-\d{2}-\d{2}T00:00$")
        from datetime import datetime

        parse = lambda v: datetime.strptime(v, "%Y-%m-%dT00:00")
        self.assertEqual(parse(start).date(), date.today())
        self.assertEqual((parse(end) - parse(start)).days, 90)

    def test_scrape_failure_is_a_500(self):
        with patch("app.bwf_client.list_all_tournaments", side_effect=Boom("refused")):
            resp = self.client.get("/admin/search-tournaments")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json(), {"success": False, "error": "refused"})

    def test_unauthenticated_request_never_scrapes(self):
        import app
        with patch("app.bwf_client.list_all_tournaments") as mocked:
            resp = app.app.test_client().get("/admin/search-tournaments")
        self.assertEqual(resp.status_code, 401)
        mocked.assert_not_called()


class TestAllBwfTournamentsEndpoint(unittest.TestCase):
    """/api/bwf-tournaments-all: calendar scrape, then a detail scrape per hit."""

    def setUp(self):
        import app
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = True

    def _empty_db(self):
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        return conn, cur

    def test_each_tournament_is_scraped_once_and_inserted(self):
        conn, cur = self._empty_db()
        # The calendar dates deliberately differ from the detail page's
        # competition_start/end: the insert takes date_start/date_end from here.
        found = [{"name": "Vikingaslaget", "url": TOURNAMENT_URL, "location": "Sollentuna",
                  "date_start": "2026-03-05", "date_end": "2026-03-06"}]
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.list_all_tournaments", return_value=found) as listed, \
             patch("app.bwf_client.fetch_tournament_details",
                   return_value=TOURNAMENT_INFO) as detailed, \
             patch("app.ext_requests.Session") as mock_session_cls:
            resp = self.client.get("/api/bwf-tournaments-all?force=true")

        self.assertEqual(resp.status_code, 200)
        listed.assert_called_once()
        detailed.assert_called_once_with(TOURNAMENT_URL)
        mock_session_cls.assert_not_called()

        inserts = [c[0] for c in cur.execute.call_args_list
                   if "INSERT INTO tournaments" in c[0][0]]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1], (
            TOURNAMENT_URL, "Vikingaslaget", "Sollentuna", "2026-03-05", "2026-03-06",
            "2026-01-01", "2026-02-01", "2026-02-10", "2026-03-01", "2026-03-02",
            json.dumps({
                "singles_levels": ["DS B", "HS A"],
                "doubles_levels": ["DD B", "HD A"],
                "mixed_levels": ["MD C"],
                "doubles_partner": ["Partner A", "Partner B", "Partner C"],
                "mixed_partner": ["Partner A", "Partner B", "Partner C"],
            }),
        ))

        self.assertEqual(resp.get_json(), {"success": True, "tournaments": [{
            "name": "Vikingaslaget", "url": TOURNAMENT_URL, "location": "Sollentuna",
            "date_start": "2026-03-05", "date_end": "2026-03-06",
            "selected_for_view": 0, "admin_reg_end_date": "",
            "tournament_groups": [], "registration_closes": ""}]})

    def test_a_tournament_whose_page_fails_is_skipped_not_wiped(self):
        conn, cur = self._empty_db()
        found = [{"name": "Vikingaslaget", "url": TOURNAMENT_URL, "location": "Sollentuna",
                  "date_start": "2026-03-01", "date_end": "2026-03-02"}]
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.list_all_tournaments", return_value=found), \
             patch("app.bwf_client.fetch_tournament_details", side_effect=Boom("refused")):
            resp = self.client.get("/api/bwf-tournaments-all?force=true")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            [c[0] for c in cur.execute.call_args_list
             if "INSERT INTO tournaments" in c[0][0]], [])

    def test_a_cached_day_scrapes_nothing(self):
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchone.return_value = (1,)
        cur.fetchall.return_value = [(
            TOURNAMENT_URL, "Vikingaslaget", "Sollentuna", "2026-03-01", "2026-03-02",
            1, "2026-02-01", None, None, 0)]
        with patch("app.sqlite3.connect", return_value=conn), \
             patch("app.bwf_client.list_all_tournaments") as listed, \
             patch("app.bwf_client.fetch_tournament_details") as detailed:
            resp = self.client.get("/api/bwf-tournaments-all")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["cached"])
        listed.assert_not_called()
        detailed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
