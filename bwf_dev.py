"""
Fake Badminton Sweden data for local development.

Imports no network library, on purpose: if anything here tries to reach the
internet, that is a bug, and the absence of an import makes it obvious.
"""

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


def get_player_license(player_name):
    raise NotImplementedError("Stub added in Task 12")


def get_player_ranking(player_name):
    raise NotImplementedError("Stub added in Task 12")


def login(username, password):
    raise NotImplementedError("Stub added in Task 12")


def verify_credentials(username, password):
    raise NotImplementedError("Stub added in Task 12")


def search_players(query):
    raise NotImplementedError("Stub added in Task 12")


def get_player_details(profile_url):
    raise NotImplementedError("Stub added in Task 12")


def get_player_ranking_by_profile(profile_url):
    raise NotImplementedError("Stub added in Task 12")


def get_tournament_events(tournament_id):
    raise NotImplementedError("Stub added in Task 12")


def fetch_tournament_info(url):
    raise NotImplementedError("Stub added in Task 12")


def fetch_tournament_details(url):
    raise NotImplementedError("Stub added in Task 12")


def search_tournaments(start, end, status):
    raise NotImplementedError("Stub added in Task 12")


def list_all_tournaments(start_date, end_date):
    raise NotImplementedError("Stub added in Task 12")


def get_tournament_medals(tournament_id):
    raise NotImplementedError("Stub added in Task 12")


def get_tournament_player_id(tournament_id, player_name):
    raise NotImplementedError("Stub added in Task 12")


def get_tournament_player_results(tournament_id, player_id):
    raise NotImplementedError("Stub added in Task 12")


def get_tournament_clubs(tournament_id):
    raise NotImplementedError("Stub added in Task 12")


def get_player_profile_by_license(license_id):
    raise NotImplementedError("Stub added in Task 12")


def submit_registrations(tournament_name, club_login, club_password):
    raise NotImplementedError("Stub added in Task 12")
