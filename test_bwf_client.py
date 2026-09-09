"""
Characterization tests for the Badminton Sweden boundary.

These describe what the scraping code does today. They are the safety net for
moving it out of app.py: behaviour must not change during the move.
"""

import json
import unittest
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


if __name__ == "__main__":
    unittest.main()
