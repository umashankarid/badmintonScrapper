"""
Unit tests for tournament data round-trip verification

Ensures that tournament data is:
1. Successfully inserted into the database
2. Can be read back correctly
3. All fields are preserved (no data loss)
4. Data integrity is maintained
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime


class TestTournamentDataRoundTrip(unittest.TestCase):
    """Test that tournament data survives round-trip to database"""

    def setUp(self):
        """Create test database"""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_tournaments.db")
        self.setup_db()

    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)

    def setup_db(self):
        """Initialize test tournaments.db"""
        conn = sqlite3.connect(self.db_path)
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

    def test_insert_and_read_back_single_tournament(self):
        """Test: Insert tournament and read it back with all data intact"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # WRITE: Insert tournament data
        original_data = {
            'tournament_url': 'https://badmintonsweden.tournamentsoftware.com/tournament/77FEC02B-4489-4D4C-A71F-C6844BAEB2BA',
            'tournament_name': 'Vikingaslaget Sollentuna',
            'location': 'Sollentuna BS | Sollentuna',
            'date_start': '2026-08-29',
            'date_end': '2026-08-30',
            'registration_opens': '2026-06-09',
            'registration_closes': '2026-08-15',
            'cancellation_deadline': '2026-08-15',
            'competition_start': '2026-08-29',
            'competition_end': '2026-08-30',
            'selected_for_view': 1
        }

        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, tuple(original_data.values()))
        conn.commit()

        # READ: Fetch tournament back
        cur.execute("""
            SELECT tournament_url, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end, selected_for_view
            FROM tournaments
            WHERE tournament_url = ?
        """, (original_data['tournament_url'],))

        row = cur.fetchone()
        col_names = ['tournament_url', 'tournament_name', 'location', 'date_start', 'date_end',
                     'registration_opens', 'registration_closes', 'cancellation_deadline',
                     'competition_start', 'competition_end', 'selected_for_view']

        result = dict(zip(col_names, row))

        # VERIFY: All data matches
        for key in original_data:
            self.assertEqual(result[key], original_data[key],
                           f"Mismatch for field '{key}': expected {original_data[key]}, got {result[key]}")

        conn.close()

    def test_date_fields_not_null_after_insert(self):
        """Test: Verify all date fields are NOT NULL after insert"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Insert tournament with all dates
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test.com/t1', 'Test Tournament', 'Test Location',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # Read back and verify no NULL values
        cur.execute("""
            SELECT registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, ('https://test.com/t1',))

        row = cur.fetchone()
        dates_values = row

        # Check none are NULL
        for i, val in enumerate(dates_values):
            self.assertIsNotNone(val, f"Date field {i} should not be NULL")
            self.assertTrue(len(val) > 0, f"Date field {i} should not be empty string")

        conn.close()

    def test_read_back_preserves_date_format(self):
        """Test: Date format is preserved in round-trip (YYYY-MM-DD)"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        test_dates = {
            'registration_opens': '2026-06-09',
            'registration_closes': '2026-08-15',
            'cancellation_deadline': '2026-08-15',
            'competition_start': '2026-08-29',
            'competition_end': '2026-08-30'
        }

        # Insert
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://format-test.com', 'Format Test', 'Location',
            test_dates['competition_start'], test_dates['competition_end'],
            test_dates['registration_opens'], test_dates['registration_closes'],
            test_dates['cancellation_deadline'],
            test_dates['competition_start'], test_dates['competition_end'],
            1
        ))
        conn.commit()

        # Read back
        cur.execute("""
            SELECT registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, ('https://format-test.com',))

        row = cur.fetchone()
        result_dates = dict(zip(test_dates.keys(), row))

        # Verify format is preserved
        import re
        iso_pattern = r'^\d{4}-\d{2}-\d{2}$'

        for field, value in result_dates.items():
            self.assertRegex(value, iso_pattern,
                           f"Field '{field}' should be in YYYY-MM-DD format, got: {value}")
            self.assertEqual(value, test_dates[field],
                           f"Field '{field}' value mismatch: expected {test_dates[field]}, got {value}")

        conn.close()

    def test_multiple_tournaments_no_data_mixing(self):
        """Test: Multiple tournaments don't cross-contaminate data"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        tournaments = [
            {
                'url': 'https://test1.com',
                'name': 'Tournament 1',
                'location': 'Location 1',
                'reg_opens': '2026-01-01',
                'reg_closes': '2026-01-31',
                'cancel': '2026-02-01',
                'comp_start': '2026-02-15',
                'comp_end': '2026-02-20'
            },
            {
                'url': 'https://test2.com',
                'name': 'Tournament 2',
                'location': 'Location 2',
                'reg_opens': '2026-03-01',
                'reg_closes': '2026-03-31',
                'cancel': '2026-04-01',
                'comp_start': '2026-04-15',
                'comp_end': '2026-04-20'
            },
            {
                'url': 'https://test3.com',
                'name': 'Tournament 3',
                'location': 'Location 3',
                'reg_opens': '2026-05-01',
                'reg_closes': '2026-05-31',
                'cancel': '2026-06-01',
                'comp_start': '2026-06-15',
                'comp_end': '2026-06-20'
            }
        ]

        # Insert all tournaments
        for t in tournaments:
            cur.execute("""
                INSERT INTO tournaments
                (tournament_url, tournament_name, location, date_start, date_end,
                 registration_opens, registration_closes, cancellation_deadline,
                 competition_start, competition_end, selected_for_view, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                t['url'], t['name'], t['location'],
                t['comp_start'], t['comp_end'],
                t['reg_opens'], t['reg_closes'], t['cancel'],
                t['comp_start'], t['comp_end'],
                1
            ))
        conn.commit()

        # Read each back and verify no mixing
        for t in tournaments:
            cur.execute("""
                SELECT tournament_name, location, registration_opens, registration_closes,
                       cancellation_deadline, competition_start, competition_end
                FROM tournaments WHERE tournament_url = ?
            """, (t['url'],))

            row = cur.fetchone()
            self.assertIsNotNone(row, f"Tournament {t['url']} should be found")

            name, loc, reg_open, reg_close, cancel, comp_start, comp_end = row

            # Verify each field
            self.assertEqual(name, t['name'], f"Name mismatch for {t['url']}")
            self.assertEqual(loc, t['location'], f"Location mismatch for {t['url']}")
            self.assertEqual(reg_open, t['reg_opens'], f"Reg opens mismatch for {t['url']}")
            self.assertEqual(reg_close, t['reg_closes'], f"Reg closes mismatch for {t['url']}")
            self.assertEqual(cancel, t['cancel'], f"Cancel mismatch for {t['url']}")
            self.assertEqual(comp_start, t['comp_start'], f"Comp start mismatch for {t['url']}")
            self.assertEqual(comp_end, t['comp_end'], f"Comp end mismatch for {t['url']}")

        conn.close()

    def test_selected_for_view_flag_persists(self):
        """Test: selected_for_view flag is correctly persisted"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Insert with selected_for_view = 1
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://visible.com', 'Visible Tournament', 'Location',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # Read back
        cur.execute("SELECT selected_for_view FROM tournaments WHERE tournament_url = ?",
                   ('https://visible.com',))
        result = cur.fetchone()[0]

        self.assertEqual(result, 1, "selected_for_view should be 1")

        conn.close()

    def test_created_at_and_last_updated_set(self):
        """Test: Timestamp fields are automatically set"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Insert
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://timestamp-test.com', 'Timestamp Test', 'Location',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # Read back
        cur.execute("SELECT created_at, last_updated FROM tournaments WHERE tournament_url = ?",
                   ('https://timestamp-test.com',))

        created_at, last_updated = cur.fetchone()

        # Verify timestamps exist and are not NULL
        self.assertIsNotNone(created_at, "created_at should not be NULL")
        self.assertIsNotNone(last_updated, "last_updated should not be NULL")
        
        # Verify timestamps are in ISO format and parseable
        import re
        iso_pattern = r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}$'
        self.assertRegex(created_at, iso_pattern, f"created_at format invalid: {created_at}")
        self.assertRegex(last_updated, iso_pattern, f"last_updated format invalid: {last_updated}")
        
        # On insert, they should be equal
        self.assertEqual(created_at, last_updated, "created_at and last_updated should be equal on insert")

        conn.close()

    def test_real_tournament_data_round_trip(self):
        """Test: Real tournament data from Badminton Sweden (Vikingaslaget Sollentuna)"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Real data from the Badminton Sweden website
        real_data = {
            'tournament_url': 'https://badmintonsweden.tournamentsoftware.com/tournament/77FEC02B-4489-4D4C-A71F-C6844BAEB2BA',
            'tournament_name': 'Vikingaslaget Sollentuna',
            'location': 'Sollentuna BS | Sollentuna',
            'date_start': '2026-08-29',
            'date_end': '2026-08-30',
            'registration_opens': '2026-06-09',
            'registration_closes': '2026-08-15',
            'cancellation_deadline': '2026-08-15',
            'competition_start': '2026-08-29',
            'competition_end': '2026-08-30'
        }

        # Insert
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            real_data['tournament_url'], real_data['tournament_name'], real_data['location'],
            real_data['date_start'], real_data['date_end'],
            real_data['registration_opens'], real_data['registration_closes'],
            real_data['cancellation_deadline'],
            real_data['competition_start'], real_data['competition_end'],
            1
        ))
        conn.commit()

        # Read back
        cur.execute("""
            SELECT tournament_url, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, (real_data['tournament_url'],))

        row = cur.fetchone()
        col_names = ['tournament_url', 'tournament_name', 'location', 'date_start', 'date_end',
                     'registration_opens', 'registration_closes', 'cancellation_deadline',
                     'competition_start', 'competition_end']
        result = dict(zip(col_names, row))

        # Verify all data matches
        for key, expected_value in real_data.items():
            actual_value = result[key]
            self.assertEqual(actual_value, expected_value,
                           f"Real data mismatch for '{key}': expected '{expected_value}', got '{actual_value}'")

        conn.close()


if __name__ == '__main__':
    unittest.main()
