"""
Fake Badminton Sweden data for local development.

Imports no network library, on purpose: if anything here tries to reach the
internet, that is a bug, and the absence of an import makes it obvious.
"""

import logging

logger = logging.getLogger(__name__)


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
