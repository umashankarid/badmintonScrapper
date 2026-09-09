"""
Fake Badminton Sweden data for local development.

Imports no network library, on purpose: if anything here tries to reach the
internet, that is a bug, and the absence of an import makes it obvious.

Every function mirrors one in bwf_live: same name, same signature, same
return type. Every stub return value that is a dict (or a list of dicts)
carries "_fake": True, so a later task can tag these rows in the UI. Plain
scalars (str, bool) that bwf_live returns un-wrapped stay un-wrapped here
too, since there is no room in a bare string to carry a flag without
changing its type. The one exception is get_player_ranking_by_profile: its
return value is written verbatim into players.ranking by a caller, so tagging
it would persist a bogus ranking category into the database, not just the UI
-- see its own docstring.
"""

import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


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


# --- Player helpers -------------------------------------------------------

def _find_player(needle):
    needle = (needle or "").strip().lower()
    if not needle:
        return None
    for p in PLAYERS:
        if needle in (p["username"].lower(), p["license_id"].lower(),
                      p["player_name"].lower()):
            return p
    return None


def _nested_ranking_json(ranking):
    """The {"singles"/"doubles"/"mixed"} int-valued shape bwf_live's
    _scrape_ranking_from_page produces, JSON-encoded.

    This is a different shape from the flat, string-valued dict that
    get_player_ranking and get_player_details return: get_player_profile_by_license
    is the only function that needs it, because it is the only one backed by
    _scrape_ranking_from_page rather than the inline table walk the other
    functions use.
    """
    nested = {"singles": {}, "doubles": {}, "mixed": {}}
    for category, values in ranking.items():
        if category in ("HS", "DS"):
            bucket = "singles"
        elif category in ("HD", "DD", "MD"):
            bucket = "doubles"
        else:
            continue
        rank = values.get("rank", "")
        points = values.get("points", "")
        nested[bucket][category] = {
            "rank": int(rank) if str(rank).isdigit() else None,
            "points": int(points) if str(points).isdigit() else 0,
        }
    return json.dumps(nested)


def get_player_license(player_name):
    player = _find_player(player_name)
    return player["license_id"] if player else ""


def get_player_ranking(player_name):
    """Returns a JSON string, matching bwf_live -- not a dict."""
    player = _find_player(player_name)
    if not player or not player["ranking"]:
        return ""
    return json.dumps(player["ranking"])


def verify_credentials(username, password):
    return login(username, password) is not None


def login(username, password):
    """Any non-empty password is accepted; the username selects the persona."""
    if not password:
        return None
    player = _find_player(username)
    if not player:
        logger.info(f"🔀 dev login rejected for unknown persona: {username}")
        return None
    logger.info(f"🔀 dev login as {player['player_name']}")
    return dict(player)


def search_players(query):
    query = (query or "").strip().lower()
    return [
        {"name": p["player_name"], "club": p["club"], "license_id": p["license_id"],
         "profile_url": p["profile_url"], "source": "live", "_fake": True}
        for p in PLAYERS
        if query and query in p["player_name"].lower() and p["license_id"]
    ]


def get_player_details(profile_url):
    for p in PLAYERS:
        if p["profile_url"] == profile_url:
            return {"gender": p["gender"], "email": p["email"],
                    "phone": p["phone"], "ranking": p["ranking"], "_fake": True}
    return {"gender": "", "email": "", "phone": "", "ranking": {}, "_fake": True}


def get_player_ranking_by_profile(profile_url):
    """Ranking dict for a known profile URL -- same flat shape as get_player_details.

    Unlike every sibling stub, this return value is never tagged "_fake":
    _register_partner (app.py) json.dumps this dict straight into
    players.ranking, so a "_fake" key here would persist as a bogus ranking
    category in the database, not just a UI hint. Unknown profile returns
    {}, not {"_fake": True}: app.py's caller does `if ranking_data:` to
    decide whether a ranking was found, so the empty dict's falsiness is the
    contract here too.
    """
    for p in PLAYERS:
        if p["profile_url"] == profile_url:
            return dict(p["ranking"])
    return {}


def get_player_profile_by_license(license_id):
    """Note: "ranking" here is a JSON string in the nested singles/doubles/mixed
    shape -- see _nested_ranking_json. That is a different type *and* a
    different shape from every other ranking-bearing function in this module."""
    for p in PLAYERS:
        if p["license_id"] == license_id:
            return {
                "name": p["player_name"], "club": p["club"], "gender": p["gender"],
                "email": p["email"], "phone": p["phone"], "dob": p["dob"],
                "age": p["age"], "ranking": _nested_ranking_json(p["ranking"]),
                "profile_url": p["profile_url"], "_fake": True,
            }
    return None


# --- Tournament helpers -----------------------------------------------------

def _tournament_id(t):
    return t["url"].rsplit("/", 1)[-1]


def _categorize_levels(levels):
    """Sort event-class strings into singles/doubles/mixed, the buckets
    bwf_live's get_tournament_events uses.

    An event string may be prefixed, as in "MJT HS U13", so match on any
    whitespace-separated token rather than only the first one.
    """
    def _has(event, codes):
        return any(token in codes for token in event.split())

    return {
        "singles_levels": [e for e in levels if _has(e, ("HS", "DS"))],
        "doubles_levels": [e for e in levels if _has(e, ("HD", "DD"))],
        "mixed_levels": [e for e in levels if _has(e, ("MD",))],
    }


def _level_tokens(levels):
    """The bare level bwf_live's get_tournament_events extracts from each
    event string via `text.split()[1]` (e.g. "HS A" -> "A"). Mirrors that
    exact token pick, quirk included: a prefixed string like "MJT HS U13"
    yields "HS", not "U13", because that is what live's own parsing does.
    """
    tokens = set()
    for event in levels:
        parts = event.split()
        if len(parts) >= 2:
            tokens.add(parts[1])
    return sorted(tokens)


def get_tournament_events(tournament_id, session=None):
    """session exists only for signature parity with bwf_live; dev mode ignores it."""
    for t in TOURNAMENTS:
        if tournament_id in t["url"]:
            result = _categorize_levels(t["levels"])
            result["levels"] = _level_tokens(t["levels"])
            result["_fake"] = True
            return result
    return {"singles_levels": [], "doubles_levels": [], "mixed_levels": [], "levels": [], "_fake": True}


def _tournament_info(t):
    info = {
        "name": t["name"],
        "location": t["location"],
        "levels": t["levels"],
        "registration_opens": t["registration_opens"],
        "registration_closes": t["registration_closes"],
        "cancellation_deadline": t["cancellation_deadline"],
        "competition_start": t["competition_start"],
        "competition_end": t["competition_end"],
        "_fake": True,
    }
    info.update(_categorize_levels(t["levels"]))
    return info


def fetch_tournament_info(url):
    """Live propagates a failing events page; dev has no failure to tolerate,
    so an unknown fixture URL is a hard error here, exactly as a scrape
    failure would be live."""
    for t in TOURNAMENTS:
        if t["url"] == url:
            return _tournament_info(t)
    raise ValueError(f"No dev tournament for {url}. Known: {[t['url'] for t in TOURNAMENTS]}")


def fetch_tournament_details(url):
    """Live tolerates a failing events page; dev mirrors that by degrading to
    an empty-but-valid result for an unknown fixture URL instead of raising."""
    for t in TOURNAMENTS:
        if t["url"] == url:
            return _tournament_info(t)
    return {
        "name": "", "location": "", "levels": [],
        "singles_levels": [], "doubles_levels": [], "mixed_levels": [],
        "registration_opens": "", "registration_closes": "",
        "cancellation_deadline": "", "competition_start": "", "competition_end": "",
        "_fake": True,
    }


def _search_result(t):
    end = date.fromisoformat(t["date_end"])
    return {
        "id": _tournament_id(t),
        "name": t["name"],
        "location": t["location"],
        "date_start": t["date_start"],
        "date_end": t["date_end"],
        "status": "Avslutad" if end < date.today() else "Anmälan öppen",
        "_fake": True,
    }


def search_tournaments(start, end, status):
    return [_search_result(t) for t in TOURNAMENTS]


def _tournament_summary(t):
    return {"name": t["name"], "url": t["url"], "location": t["location"],
            "date_start": t["date_start"], "date_end": t["date_end"], "_fake": True}


def list_all_tournaments(start_date, end_date):
    return [_tournament_summary(t) for t in TOURNAMENTS]


def get_tournament_medals(tournament_id):
    return [
        {"name": "Adam Adult", "event": "HS A", "placement": "Winner", "_fake": True},
        {"name": "Elin Elit", "event": "DS A", "placement": "Winner", "_fake": True},
    ]


def get_tournament_player_id(tournament_id, player_name):
    player = _find_player(player_name)
    return player["license_id"] if player else ""


def get_tournament_player_results(tournament_id, player_id):
    """Field names match bwf_live exactly: stats rows are category/played/
    win_loss/sets/points, match rows are round/event/team1/team2/team1_won/
    score -- these are read straight off by tournament_detail.html."""
    return {
        "stats": [{"category": "HS A", "played": "3", "win_loss": "2-1",
                    "sets": "4-2", "points": "45-30", "_fake": True}],
        "matches": [{"round": "Semifinal", "event": "HS A", "team1": "Adam Adult",
                     "team2": "Pia Partner", "team1_won": True,
                     "score": "21-15 21-18", "_fake": True}],
        "_fake": True,
    }


def get_tournament_clubs(tournament_id):
    return [{"name": p["player_name"], "club": p["club"], "player_id": p["license_id"],
             "_fake": True} for p in PLAYERS if p["license_id"]]


def submit_registrations(tournament_name, club_login, club_password):
    """Pretend the submission worked. Playwright is never launched.

    "submitted" is a list of dicts, not names: bwf_submit's real entries are
    {"player_name", "license_id", "message"}, and manage-tournaments.html /
    tournament.html read p.player_name and p.message per entry.
    """
    logger.info(f"🔀 dev submit for '{tournament_name}' — nothing was sent to Badminton Sweden")
    submitted = [
        {"player_name": p["player_name"], "license_id": p["license_id"],
         "message": "DEV MODE: pretended to submit", "_fake": True}
        for p in PLAYERS if p["license_id"]
    ]
    return {"success": True, "submitted": submitted, "failed": [],
            "message": f"DEV MODE: pretended to submit for '{tournament_name}'",
            "_fake": True}
