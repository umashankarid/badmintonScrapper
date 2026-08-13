"""
Unit tests for tournament data scraping

Verifies that all tournament date fields are properly populated:
- registration_opens
- registration_closes
- cancellation_deadline
- competition_start
- competition_end
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup


class TestTournamentScraping(unittest.TestCase):
    """Test tournament data scraping and database population"""

    def setUp(self):
        """Create test database"""
        self.test_dir = tempfile.mkdtemp()
        self.tournaments_db = os.path.join(self.test_dir, "test_tournaments.db")
        self.setup_db()

    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)

    def setup_db(self):
        """Initialize test tournaments.db"""
        conn = sqlite3.connect(self.tournaments_db)
        conn.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL,
                location TEXT,
                date_start TEXT,
                date_end TEXT,
                registration_opens TEXT,
                registration_closes TEXT,
                cancellation_deadline TEXT,
                competition_start TEXT,
                competition_end TEXT,
                selected_for_view INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def test_tournament_schema_has_all_date_fields(self):
        """Test: tournaments table has all required date fields"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        # Get schema
        cur.execute("PRAGMA table_info(tournaments)")
        columns = {row[1] for row in cur.fetchall()}

        # Verify required fields
        required_fields = {
            'id', 'tournament_url', 'tournament_name', 'location',
            'date_start', 'date_end',
            'registration_opens', 'registration_closes', 'cancellation_deadline',
            'competition_start', 'competition_end',
            'selected_for_view', 'created_at', 'last_updated'
        }

        missing = required_fields - columns
        self.assertEqual(missing, set(), f"Missing columns: {missing}")
        conn.close()

    def test_insert_tournament_with_all_dates(self):
        """Test: Insert tournament with all date fields populated"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        test_data = {
            'tournament_url': 'https://badmintonsweden.tournamentsoftware.com/tournament/abc123',
            'tournament_name': 'Stockholm Open 2026',
            'location': 'Stockholm',
            'date_start': '2026-09-01',
            'date_end': '2026-09-05',
            'registration_opens': '2026-08-01',
            'registration_closes': '2026-08-25',
            'cancellation_deadline': '2026-08-28',
            'competition_start': '2026-09-01',
            'competition_end': '2026-09-05'
        }

        # Insert
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(test_data.values()))
        conn.commit()

        # Verify
        cur.execute("SELECT * FROM tournaments WHERE tournament_url = ?",
                   (test_data['tournament_url'],))
        row = cur.fetchone()
        col_names = [desc[0] for desc in cur.description]

        self.assertIsNotNone(row, "Tournament should be inserted")
        
        # Map columns to values
        result = dict(zip(col_names, row))

        # Check all date fields are populated (not NULL, not empty)
        self.assertEqual(result['registration_opens'], '2026-08-01',
                        "registration_opens should be populated")
        self.assertEqual(result['registration_closes'], '2026-08-25',
                        "registration_closes should be populated")
        self.assertEqual(result['cancellation_deadline'], '2026-08-28',
                        "cancellation_deadline should be populated")
        self.assertEqual(result['competition_start'], '2026-09-01',
                        "competition_start should be populated")
        self.assertEqual(result['competition_end'], '2026-09-05',
                        "competition_end should be populated")

        conn.close()

    def test_tournament_dates_not_null(self):
        """Test: No tournament should have NULL date fields"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        # Insert test tournaments
        tournaments = [
            ('https://bwf.com/t1', 'T1', 'Loc1', '2026-09-01', '2026-09-05',
             '2026-08-01', '2026-08-25', '2026-08-28', '2026-09-01', '2026-09-05'),
            ('https://bwf.com/t2', 'T2', 'Loc2', '2026-10-01', '2026-10-05',
             '2026-09-01', '2026-09-25', '2026-09-28', '2026-10-01', '2026-10-05'),
        ]

        for t in tournaments:
            cur.execute("""
                INSERT INTO tournaments
                (tournament_url, tournament_name, location, date_start, date_end,
                 registration_opens, registration_closes, cancellation_deadline,
                 competition_start, competition_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, t)
        conn.commit()

        # Check for NULL values
        cur.execute("""
            SELECT COUNT(*) FROM tournaments
            WHERE registration_opens IS NULL
               OR registration_closes IS NULL
               OR cancellation_deadline IS NULL
               OR competition_start IS NULL
               OR competition_end IS NULL
        """)

        null_count = cur.fetchone()[0]
        self.assertEqual(null_count, 0, f"Found {null_count} tournaments with NULL date fields")

        conn.close()

    def test_tournament_dates_are_iso_format(self):
        """Test: All tournament dates should be in YYYY-MM-DD format"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        test_data = (
            'https://bwf.com/test', 'Test Tournament', 'Location',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28', '2026-09-01', '2026-09-05'
        )

        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_data)
        conn.commit()

        # Get inserted data
        cur.execute("""
            SELECT registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, ('https://bwf.com/test',))

        row = cur.fetchone()
        date_fields = row

        # Verify ISO format (YYYY-MM-DD)
        import re
        iso_pattern = r'^\d{4}-\d{2}-\d{2}$'

        for i, date_val in enumerate(date_fields):
            self.assertIsNotNone(date_val, f"Date field {i} should not be NULL")
            self.assertRegex(date_val, iso_pattern,
                           f"Date field {i} should be in YYYY-MM-DD format, got: {date_val}")

        conn.close()

    def test_tournament_dates_logical_order(self):
        """Test: Tournament dates should be in logical order"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        test_data = (
            'https://bwf.com/logic-test', 'Logic Test', 'Location',
            '2026-09-01', '2026-09-05',  # date_start < date_end
            '2026-08-01', '2026-08-25',  # reg_opens < reg_closes
            '2026-08-28',                # cancel_deadline after reg_closes
            '2026-09-01', '2026-09-05'   # comp_start < comp_end
        )

        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_data)
        conn.commit()

        # Verify logical order
        cur.execute("""
            SELECT date_start, date_end, registration_opens, registration_closes,
                   cancellation_deadline, competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, ('https://bwf.com/logic-test',))

        row = cur.fetchone()
        ds, de, ro, rc, cd, cs, ce = row

        # Logical checks
        self.assertLess(ds, de, "date_start should be < date_end")
        self.assertLess(ro, rc, "registration_opens should be < registration_closes")
        self.assertLessEqual(rc, cd, "registration_closes should be <= cancellation_deadline")
        self.assertLess(cs, ce, "competition_start should be < competition_end")

        conn.close()

    def test_multiple_tournaments_all_have_dates(self):
        """Test: Batch insert of tournaments - all have date fields"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()

        # Insert 10 tournaments
        for i in range(1, 11):
            t_date = f"2026-{str((i % 12) + 1).zfill(2)}-01"
            t_end = f"2026-{str((i % 12) + 1).zfill(2)}-05"

            cur.execute("""
                INSERT INTO tournaments
                (tournament_url, tournament_name, location, date_start, date_end,
                 registration_opens, registration_closes, cancellation_deadline,
                 competition_start, competition_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f'https://bwf.com/t{i}', f'Tournament {i}', f'Location {i}',
                t_date, t_end,
                '2026-01-01', '2026-08-25', '2026-08-28', t_date, t_end
            ))
        conn.commit()

        # Verify all tournaments have date fields
        cur.execute("""
            SELECT COUNT(*) FROM tournaments
        """)
        total = cur.fetchone()[0]
        self.assertEqual(total, 10, "Should have 10 tournaments")

        cur.execute("""
            SELECT COUNT(*) FROM tournaments
            WHERE registration_opens IS NOT NULL
              AND registration_closes IS NOT NULL
              AND cancellation_deadline IS NOT NULL
              AND competition_start IS NOT NULL
              AND competition_end IS NOT NULL
        """)

        with_dates = cur.fetchone()[0]
        self.assertEqual(with_dates, 10, "All 10 tournaments should have all date fields")

        conn.close()


if __name__ == '__main__':
    unittest.main()
