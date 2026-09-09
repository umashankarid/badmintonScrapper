"""Seeded state actually lands in SQLite the way the browser tests expect.

Every test here requests app_server, not just data_dir: the tables these
helpers write to don't exist until app.py imports and runs its init_*_db()
functions, so seeding against a bare data_dir would fail with
"no such table". Booting the server is what creates the schema.
"""

from datetime import date

from tests.e2e import seed


def test_open_tournament_is_visible_and_future(data_dir, app_server):
    name = seed.open_tournament(data_dir)
    rows = seed.tournaments(data_dir)
    row = next(r for r in rows if r["tournament_name"] == name)
    assert row["selected_for_view"] == 1
    assert date.fromisoformat(row["registration_closes"]) > date.today()
    assert date.fromisoformat(row["date_start"]) > date.today()


def test_past_tournament_is_closed(data_dir, app_server):
    name = seed.past_tournament(data_dir)
    row = next(r for r in seed.tournaments(data_dir) if r["tournament_name"] == name)
    assert date.fromisoformat(row["registration_closes"]) < date.today()


def test_registration_round_trips(data_dir, app_server):
    name = seed.open_tournament(data_dir, name="Round Trip Cup")
    seed.registration(data_dir, name, "DEV-0001", singles="HS A")
    rows = seed.registrations_for(data_dir, name)
    assert len(rows) == 1
    assert rows[0]["license_id"] == "DEV-0001"
    assert rows[0]["singles_levels"] == "HS A"
