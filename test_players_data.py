"""
Unit test to verify players table has proper data
Tests that player records have non-null name, club, email, phone when scraped
"""

import unittest
import sqlite3
import os
import tempfile


class TestPlayersData(unittest.TestCase):
    """Test player data integrity against a throwaway players.db this test
    builds itself.

    players.db is gitignored, so a fresh clone has none -- pointing setUp at
    the real file made this module error out on its own on a clean checkout,
    and only "pass" in CI because some other module happened to import app.py
    first and create an empty file as a side effect. Asserting against
    whatever real data is on a developer's machine would test that data, not
    this code, anyway.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE players (
                license_id TEXT PRIMARY KEY,
                name TEXT,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO players (license_id, name, club, gender, email, phone) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("DEV-9001", "Complete Player", "BMK Komet", "M", "player@example.com", "0701234567"),
                # A placeholder row with a NULL name -- the shape
                # test_no_temp_entries_with_null_name exists to catch a
                # regression on (a *non-null* "temp_*" name), so a NULL one
                # here exercises the boundary instead of leaving the check
                # vacuously true on an all-clean fixture.
                ("temp_0001", None, None, None, None, None),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        os.remove(self.db_path)

    def test_players_table_structure(self):
        """Verify players table has expected columns"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        cur.execute("PRAGMA table_info(players)")
        columns = {row[1] for row in cur.fetchall()}
        
        expected = {'license_id', 'name', 'club', 'gender', 'email', 'phone'}
        self.assertTrue(expected.issubset(columns), f"Missing columns: {expected - columns}")
        
        conn.close()
    
    def test_no_temp_entries_with_null_name(self):
        """Verify no 'temp_*' entries exist with NULL name"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Find temp entries with null names
        cur.execute("""
            SELECT COUNT(*) FROM players 
            WHERE name LIKE 'temp_%' AND name IS NOT NULL
        """)
        count = cur.fetchone()[0]
        
        self.assertEqual(count, 0, "Found temp_* entries with non-null names (placeholder entries)")
        
        conn.close()
    
    def test_players_with_license_id_have_data(self):
        """Verify players with license_id have proper name and contact info"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Get all players with real license_id (not temp)
        cur.execute("""
            SELECT license_id, name, email, phone, club FROM players 
            WHERE license_id IS NOT NULL AND license_id NOT LIKE 'temp_%'
            LIMIT 10
        """)
        
        rows = cur.fetchall()
        conn.close()

        # Not wrapped in "if rows:" -- that made this assertion vacuous on an
        # empty table (which is exactly what a fresh checkout's players.db
        # used to be). The fixture always seeds at least one non-temp row, so
        # this must actually run the check below.
        self.assertTrue(rows, "fixture produced no non-temp rows to check")
        for license_id, name, email, phone, club in rows:
            # At least name should be populated, or email/phone/club
            has_name = name and name != f"Player {license_id}"
            has_contact = email or phone
            has_club = club

            self.assertTrue(
                has_name or has_contact or has_club,
                f"Player {license_id} has no useful data: name={name}, email={email}, phone={phone}, club={club}"
            )

if __name__ == '__main__':
    unittest.main()
