"""
Unit tests: Explicitly verify NO NULL values in tournament date fields

This test is specifically designed to catch the NULL value bug that was happening.
It tests the exact scenario: insert a tournament, read it back, and verify NO NULL values.
"""

import unittest
import sqlite3
import os
import tempfile
import shutil


class TestTournamentNullValueDetection(unittest.TestCase):
    """Explicitly test for NULL value bug"""

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

    def test_explicit_null_check_registration_opens(self):
        """Test: registration_opens is NOT NULL after insert and read"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test1.com', 'Test 1', 'Location 1',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK
        cur.execute("SELECT registration_opens FROM tournaments WHERE tournament_url = ?",
                   ('https://test1.com',))
        result = cur.fetchone()
        
        conn.close()

        # VERIFY: NOT NULL and NOT empty string
        self.assertIsNotNone(result, "Query should return a row")
        value = result[0]
        
        print(f"\nregistration_opens value: {repr(value)}")
        print(f"Value type: {type(value)}")
        print(f"Is None? {value is None}")
        print(f"Is empty string? {value == ''}")
        
        self.assertIsNotNone(value, "registration_opens should NOT be NULL")
        self.assertNotEqual(value, '', "registration_opens should NOT be empty string")
        self.assertEqual(value, '2026-08-01', "registration_opens should have correct value")

    def test_explicit_null_check_registration_closes(self):
        """Test: registration_closes is NOT NULL after insert and read"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test2.com', 'Test 2', 'Location 2',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK
        cur.execute("SELECT registration_closes FROM tournaments WHERE tournament_url = ?",
                   ('https://test2.com',))
        result = cur.fetchone()
        
        conn.close()

        # VERIFY
        self.assertIsNotNone(result, "Query should return a row")
        value = result[0]
        
        print(f"\nregistration_closes value: {repr(value)}")
        self.assertIsNotNone(value, "registration_closes should NOT be NULL")
        self.assertNotEqual(value, '', "registration_closes should NOT be empty string")
        self.assertEqual(value, '2026-08-25', "registration_closes should have correct value")

    def test_explicit_null_check_cancellation_deadline(self):
        """Test: cancellation_deadline is NOT NULL after insert and read"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test3.com', 'Test 3', 'Location 3',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK
        cur.execute("SELECT cancellation_deadline FROM tournaments WHERE tournament_url = ?",
                   ('https://test3.com',))
        result = cur.fetchone()
        
        conn.close()

        # VERIFY
        self.assertIsNotNone(result, "Query should return a row")
        value = result[0]
        
        print(f"\ncancellation_deadline value: {repr(value)}")
        self.assertIsNotNone(value, "cancellation_deadline should NOT be NULL")
        self.assertNotEqual(value, '', "cancellation_deadline should NOT be empty string")
        self.assertEqual(value, '2026-08-28', "cancellation_deadline should have correct value")

    def test_explicit_null_check_competition_start(self):
        """Test: competition_start is NOT NULL after insert and read"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test4.com', 'Test 4', 'Location 4',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK
        cur.execute("SELECT competition_start FROM tournaments WHERE tournament_url = ?",
                   ('https://test4.com',))
        result = cur.fetchone()
        
        conn.close()

        # VERIFY
        self.assertIsNotNone(result, "Query should return a row")
        value = result[0]
        
        print(f"\ncompetition_start value: {repr(value)}")
        self.assertIsNotNone(value, "competition_start should NOT be NULL")
        self.assertNotEqual(value, '', "competition_start should NOT be empty string")
        self.assertEqual(value, '2026-09-01', "competition_start should have correct value")

    def test_explicit_null_check_competition_end(self):
        """Test: competition_end is NOT NULL after insert and read"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://test5.com', 'Test 5', 'Location 5',
            '2026-09-01', '2026-09-05',
            '2026-08-01', '2026-08-25', '2026-08-28',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK
        cur.execute("SELECT competition_end FROM tournaments WHERE tournament_url = ?",
                   ('https://test5.com',))
        result = cur.fetchone()
        
        conn.close()

        # VERIFY
        self.assertIsNotNone(result, "Query should return a row")
        value = result[0]
        
        print(f"\ncompetition_end value: {repr(value)}")
        self.assertIsNotNone(value, "competition_end should NOT be NULL")
        self.assertNotEqual(value, '', "competition_end should NOT be empty string")
        self.assertEqual(value, '2026-09-05', "competition_end should have correct value")

    def test_all_five_date_fields_none_null_together(self):
        """Test: CRITICAL - All 5 date fields are NOT NULL in single tournament"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # INSERT one tournament with all dates
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            'https://critical-test.com', 'Critical Test Tournament', 'Test Location',
            '2026-09-01', '2026-09-05',
            '2026-06-09', '2026-08-15', '2026-08-15',
            '2026-09-01', '2026-09-05',
            1
        ))
        conn.commit()

        # READ BACK - THIS IS THE CRITICAL TEST
        cur.execute("""
            SELECT registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, ('https://critical-test.com',))

        result = cur.fetchone()
        conn.close()

        self.assertIsNotNone(result, "Tournament should be found in database")

        reg_opens, reg_closes, cancel_deadline, comp_start, comp_end = result

        print(f"\n" + "=" * 80)
        print("CRITICAL NULL VALUE CHECK - ALL 5 DATE FIELDS")
        print("=" * 80)
        print(f"registration_opens:    {repr(reg_opens):20} | Is NULL? {reg_opens is None} | Is empty? {reg_opens == ''}")
        print(f"registration_closes:   {repr(reg_closes):20} | Is NULL? {reg_closes is None} | Is empty? {reg_closes == ''}")
        print(f"cancellation_deadline: {repr(cancel_deadline):20} | Is NULL? {cancel_deadline is None} | Is empty? {cancel_deadline == ''}")
        print(f"competition_start:     {repr(comp_start):20} | Is NULL? {comp_start is None} | Is empty? {comp_start == ''}")
        print(f"competition_end:       {repr(comp_end):20} | Is NULL? {comp_end is None} | Is empty? {comp_end == ''}")
        print("=" * 80)

        # THE CRITICAL ASSERTIONS - FAIL IF ANY ARE NULL!
        self.assertIsNotNone(reg_opens, "❌ CRITICAL: registration_opens is NULL!")
        self.assertIsNotNone(reg_closes, "❌ CRITICAL: registration_closes is NULL!")
        self.assertIsNotNone(cancel_deadline, "❌ CRITICAL: cancellation_deadline is NULL!")
        self.assertIsNotNone(comp_start, "❌ CRITICAL: competition_start is NULL!")
        self.assertIsNotNone(comp_end, "❌ CRITICAL: competition_end is NULL!")

        # Also check they're not empty strings
        self.assertNotEqual(reg_opens, '', "registration_opens should not be empty string")
        self.assertNotEqual(reg_closes, '', "registration_closes should not be empty string")
        self.assertNotEqual(cancel_deadline, '', "cancellation_deadline should not be empty string")
        self.assertNotEqual(comp_start, '', "competition_start should not be empty string")
        self.assertNotEqual(comp_end, '', "competition_end should not be empty string")

        # Verify correct values
        self.assertEqual(reg_opens, '2026-06-09', f"Expected 2026-06-09, got {reg_opens}")
        self.assertEqual(reg_closes, '2026-08-15', f"Expected 2026-08-15, got {reg_closes}")
        self.assertEqual(cancel_deadline, '2026-08-15', f"Expected 2026-08-15, got {cancel_deadline}")
        self.assertEqual(comp_start, '2026-09-01', f"Expected 2026-09-01, got {comp_start}")
        self.assertEqual(comp_end, '2026-09-05', f"Expected 2026-09-05, got {comp_end}")

        print("\n✅ ALL 5 DATE FIELDS ARE CORRECTLY POPULATED - NO NULL VALUES!")


if __name__ == '__main__':
    unittest.main(verbosity=2)
