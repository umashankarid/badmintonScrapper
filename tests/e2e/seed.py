"""Every SQL write the browser tests need, in one place.

The tests seed SQLite directly rather than driving the admin UI: faster, and
it can construct states the UI cannot reach. The cost is that these functions
know the schema, so a migration breaks this file -- which is exactly why every
write lives here and nowhere else.

Dates are always relative to today. A hardcoded year silently turns an
open-registration fixture into a closed one.
"""

import json
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path


def _connect(data_dir: Path):
    conn = sqlite3.connect(Path(data_dir) / "tournaments.db", timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _execute(data_dir, db_name, sql, params):
    """Run one write against `db_name` in data_dir, retrying briefly on lock.

    The app server owns the same SQLite files while it's running, so a write
    from here can occasionally collide with one of its own. A few retries
    with a short backoff clears it without restructuring the fixtures. One
    helper for every db this module writes to (tournaments.db, players.db),
    rather than three copies of the same loop.
    """
    # ponytail: retry loop is a lock workaround, not a queue -- fine at this
    # test-suite scale; replace with a real writer lock if seeds grow heavy.
    attempts = 5
    for attempt in range(attempts):
        conn = sqlite3.connect(Path(data_dir) / db_name, timeout=5)
        try:
            conn.execute(sql, params)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < attempts - 1:
                time.sleep(0.2 * (attempt + 1))
                continue
            raise
        finally:
            conn.close()


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


DEFAULT_CATEGORIES = {
    "singles_levels": ["HS A", "HS B", "DS A", "DS B"],
    "doubles_levels": ["HD B", "DD B"],
    "mixed_levels": ["MD B"],
    "doubles_partner": [],
    "mixed_partner": [],
}


def _insert_tournament(data_dir, name, url, start, reg_closes, categories, groups,
                        selected_for_view=1):
    # registration_opens is derived from reg_closes rather than a second
    # hardcoded offset: a tournament fixture whose closing date moves (e.g.
    # past_tournament's -40 days) must never end up with registration
    # opening *after* it closes.
    reg_opens = (date.fromisoformat(reg_closes) - timedelta(days=14)).isoformat()
    # last_updated is set explicitly to a local-date string rather than left
    # to the column's own DEFAULT CURRENT_TIMESTAMP (SQLite's CURRENT_TIMESTAMP
    # is UTC). app.py's same-day-cache check compares it against a local
    # date string (datetime.now(), no tz) -- between 00:00 and 02:00 in
    # Europe/Stockholm the two dates disagree, the cache misses, and the
    # resulting fresh-fetch branch deletes expired tournaments (and their
    # registrations) from the shared session database.
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _execute(
        data_dir, "tournaments.db",
        "INSERT OR REPLACE INTO tournaments "
        "(tournament_name, tournament_url, location, date_start, date_end, "
        " registration_opens, registration_closes, cancellation_deadline, "
        " competition_start, competition_end, categories, selected_for_view, "
        " tournament_groups, last_updated) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, url, "Testville", start, start,
         reg_opens, reg_closes, reg_closes, start, start,
         json.dumps(categories), selected_for_view,
         json.dumps(groups) if groups else None, last_updated))
    return name


def open_tournament(data_dir, name="Test Open", groups=None, selected_for_view=1):
    """Registration open, competition in the future.

    selected_for_view defaults to visible; pass 0 to build a hidden-but-
    otherwise-open fixture -- the real negative case for the flag itself,
    as opposed to past_tournament's exclusion-by-date.
    """
    return _insert_tournament(
        data_dir, name, f"https://dev.local/tournament/{name.replace(' ', '-')}",
        _day(30), _day(14), DEFAULT_CATEGORIES, groups, selected_for_view)


def past_tournament(data_dir, name="Test Past Cup"):
    """Registration closed, competition already happened."""
    return _insert_tournament(
        data_dir, name, f"https://dev.local/tournament/{name.replace(' ', '-')}",
        _day(-30), _day(-40), DEFAULT_CATEGORIES, None)


def registration(data_dir, tournament, license_id, singles="HS B"):
    _execute(
        data_dir, "tournaments.db",
        "INSERT OR REPLACE INTO tournament_registrations "
        "(tournament_name, license_id, singles_levels) VALUES (?,?,?)",
        (tournament, license_id, singles))


def player(data_dir, license_id, name, club="BMK Komet"):
    """A row in players.db's `players` table -- the one /api/tournament-players
    LEFT JOINs a registration's license_id against to get a display name.
    seed.registration() deliberately skips this (that's what makes GHOST-*
    licences orphans for the cleanup tests), so any test that needs a real
    name on screen -- not "Unknown" -- seeds it here too.

    Keyed on profile_url, the column that actually carries a UNIQUE
    constraint on this table (license_id does not): INSERT OR REPLACE on
    license_id alone would just pile up duplicate rows and break the join
    into returning one row per registration twice over. The URL shape
    matches bwf_dev.py's own fixtures, so this coexists cleanly with a row
    the real login path (_persist_login_profile) writes for the same player.
    """
    _execute(
        data_dir, "players.db",
        "INSERT OR REPLACE INTO players (license_id, name, profile_url, club) "
        "VALUES (?,?,?,?)",
        (license_id, name, f"/player-profile/{license_id}", club))


def komet_player(data_dir, license_id, name, groups):
    _execute(
        data_dir, "players.db",
        "INSERT OR REPLACE INTO kometPlayers (license_id, name, groups) "
        "VALUES (?,?,?)",
        (license_id, name, json.dumps(groups)))


def tournaments(data_dir):
    conn = _connect(data_dir)
    rows = [dict(r) for r in conn.execute("SELECT * FROM tournaments")]
    conn.close()
    return rows


def registrations_for(data_dir, tournament):
    conn = _connect(data_dir)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM tournament_registrations WHERE tournament_name = ?",
        (tournament,))]
    conn.close()
    return rows
