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
from datetime import date, timedelta
from pathlib import Path


def _connect(data_dir: Path):
    conn = sqlite3.connect(Path(data_dir) / "tournaments.db", timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _execute(data_dir, sql, params):
    """Run one write against tournaments.db, retrying briefly on lock.

    The app server owns the same SQLite file while it's running, so a write
    from here can occasionally collide with one of its own. A few retries
    with a short backoff clears it without restructuring the fixtures.
    """
    # ponytail: retry loop is a lock workaround, not a queue -- fine at this
    # test-suite scale; replace with a real writer lock if seeds grow heavy.
    attempts = 5
    for attempt in range(attempts):
        conn = _connect(data_dir)
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


def _insert_tournament(data_dir, name, url, start, reg_closes, categories, groups):
    _execute(
        data_dir,
        "INSERT OR REPLACE INTO tournaments "
        "(tournament_name, tournament_url, location, date_start, date_end, "
        " registration_opens, registration_closes, cancellation_deadline, "
        " competition_start, competition_end, categories, selected_for_view, "
        " tournament_groups) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
        (name, url, "Testville", start, start,
         _day(-30), reg_closes, reg_closes, start, start,
         json.dumps(categories), json.dumps(groups) if groups else None))
    return name


def open_tournament(data_dir, name="Test Open", groups=None):
    """Registration open, competition in the future."""
    return _insert_tournament(
        data_dir, name, f"https://dev.local/tournament/{name.replace(' ', '-')}",
        _day(30), _day(14), DEFAULT_CATEGORIES, groups)


def sjt_tournament(data_dir, name="Test SJT Cup"):
    """Name contains SJT, so the MJT/SJT level rules apply."""
    categories = {
        "singles_levels": ["HS U15", "MJT HS U13"],
        "doubles_levels": [], "mixed_levels": [],
        "doubles_partner": [], "mixed_partner": [],
    }
    return _insert_tournament(
        data_dir, name, f"https://dev.local/tournament/{name.replace(' ', '-')}",
        _day(45), _day(21), categories, None)


def past_tournament(data_dir, name="Test Past Cup"):
    """Registration closed, competition already happened."""
    return _insert_tournament(
        data_dir, name, f"https://dev.local/tournament/{name.replace(' ', '-')}",
        _day(-30), _day(-40), DEFAULT_CATEGORIES, None)


def registration(data_dir, tournament, license_id, singles="HS B"):
    _execute(
        data_dir,
        "INSERT OR REPLACE INTO tournament_registrations "
        "(tournament_name, license_id, singles_levels) VALUES (?,?,?)",
        (tournament, license_id, singles))


def komet_player(data_dir, license_id, name, groups):
    attempts = 5
    for attempt in range(attempts):
        conn = sqlite3.connect(Path(data_dir) / "players.db", timeout=5)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO kometPlayers (license_id, name, groups) "
                "VALUES (?,?,?)",
                (license_id, name, json.dumps(groups)))
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < attempts - 1:
                time.sleep(0.2 * (attempt + 1))
                continue
            raise
        finally:
            conn.close()


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
