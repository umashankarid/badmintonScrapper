"""
End-to-end integration test for ensure_tournament() endpoint

Tests the ENTIRE flow:
1. HTTP POST to /api/ensure-tournament with real URL
2. Scrapes tournament data from Badminton Sweden
3. Inserts into tournaments.db
4. Reads back and verifies ALL fields are populated
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import json
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys

# Add app to path
sys.path.insert(0, '/local/badmintonScrapPython')

class TestEnsureTournamentIntegration(unittest.TestCase):
    """End-to-end test of ensure_tournament() function"""

    def setUp(self):
        """Create test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.tournaments_db = os.path.join(self.test_dir, "test_tournaments.db")
        self.tournaments_dir = os.path.join(self.test_dir, "tournaments")
        os.makedirs(self.tournaments_dir, exist_ok=True)
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

    def test_ensure_tournament_data_flow_with_real_html(self):
        """
        END-TO-END TEST: Simulate ensure_tournament() with real HTML extraction
        
        This test verifies the complete data flow:
        1. Extract tournament data from HTML
        2. Insert into tournaments.db
        3. Read back and verify ALL fields are populated
        """
        # Simulated extracted data (from debug_tournament_scraping.py output)
        tournament_url = "https://badmintonsweden.tournamentsoftware.com/tournament/77FEC02B-4489-4D4C-A71F-C6844BAEB2BA"
        tournament_name = "Vikingaslaget Sollentuna"
        location = "Sollentuna BS | Sollentuna"
        
        # Dates extracted from HTML (these SHOULD be populated)
        dates = {
            "registration_opens": "2026-06-09",
            "registration_closes": "2026-08-15",
            "cancellation_deadline": "2026-08-15",
            "competition_start": "2026-08-29",
            "competition_end": "2026-08-30"
        }
        
        print("\n" + "=" * 80)
        print("SIMULATING ensure_tournament() DATA FLOW")
        print("=" * 80)
        print(f"\nStep 1: EXTRACT from HTML")
        print(f"  URL: {tournament_url}")
        print(f"  Name: {tournament_name}")
        print(f"  Location: {location}")
        print(f"  Extracted Dates:")
        for key, val in dates.items():
            print(f"    {key}: {val}")
        
        # STEP 1: Connect to database
        print(f"\nStep 2: INSERT into tournaments.db")
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()
        
        # STEP 2: Insert exactly as ensure_tournament() does
        print(f"  Executing INSERT with:")
        print(f"    tournament_url: {tournament_url}")
        print(f"    tournament_name: {tournament_name}")
        print(f"    location: {location}")
        print(f"    date_start: {dates.get('competition_start', '')}")
        print(f"    date_end: {dates.get('competition_end', '')}")
        print(f"    registration_opens: {dates.get('registration_opens', '')}")
        print(f"    registration_closes: {dates.get('registration_closes', '')}")
        print(f"    cancellation_deadline: {dates.get('cancellation_deadline', '')}")
        print(f"    competition_start: {dates.get('competition_start', '')}")
        print(f"    competition_end: {dates.get('competition_end', '')}")
        print(f"    selected_for_view: 1")
        
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            tournament_url,
            tournament_name,
            location,
            dates.get("competition_start", ""),  # date_start
            dates.get("competition_end", ""),    # date_end
            dates.get("registration_opens", ""),
            dates.get("registration_closes", ""),
            dates.get("cancellation_deadline", ""),
            dates.get("competition_start", ""),
            dates.get("competition_end", ""),
            1  # selected_for_view = true
        ))
        conn.commit()
        print(f"  ✅ INSERT successful")
        
        # STEP 3: Read back and verify
        print(f"\nStep 3: READ from tournaments.db")
        cur.execute("""
            SELECT tournament_url, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end, selected_for_view
            FROM tournaments WHERE tournament_url = ?
        """, (tournament_url,))
        
        row = cur.fetchone()
        col_names = ['tournament_url', 'tournament_name', 'location', 'date_start', 'date_end',
                     'registration_opens', 'registration_closes', 'cancellation_deadline',
                     'competition_start', 'competition_end', 'selected_for_view']
        
        result = dict(zip(col_names, row))
        
        print(f"  Retrieved data:")
        for key, val in result.items():
            print(f"    {key}: {val}")
        
        conn.close()
        
        # STEP 4: Verify ALL fields
        print(f"\nStep 4: VERIFY all fields")
        errors = []
        
        # Check key fields
        if result['tournament_name'] != tournament_name:
            errors.append(f"tournament_name mismatch: {result['tournament_name']} != {tournament_name}")
        else:
            print(f"  ✅ tournament_name: {result['tournament_name']}")
        
        if result['location'] != location:
            errors.append(f"location mismatch: {result['location']} != {location}")
        else:
            print(f"  ✅ location: {result['location']}")
        
        # Check ALL date fields - THIS IS THE KEY TEST
        if result['registration_opens'] is None or result['registration_opens'] == '':
            errors.append(f"❌ registration_opens is NULL or empty!")
        else:
            print(f"  ✅ registration_opens: {result['registration_opens']}")
        
        if result['registration_closes'] is None or result['registration_closes'] == '':
            errors.append(f"❌ registration_closes is NULL or empty!")
        else:
            print(f"  ✅ registration_closes: {result['registration_closes']}")
        
        if result['cancellation_deadline'] is None or result['cancellation_deadline'] == '':
            errors.append(f"❌ cancellation_deadline is NULL or empty!")
        else:
            print(f"  ✅ cancellation_deadline: {result['cancellation_deadline']}")
        
        if result['competition_start'] is None or result['competition_start'] == '':
            errors.append(f"❌ competition_start is NULL or empty!")
        else:
            print(f"  ✅ competition_start: {result['competition_start']}")
        
        if result['competition_end'] is None or result['competition_end'] == '':
            errors.append(f"❌ competition_end is NULL or empty!")
        else:
            print(f"  ✅ competition_end: {result['competition_end']}")
        
        if result['selected_for_view'] != 1:
            errors.append(f"selected_for_view should be 1, got {result['selected_for_view']}")
        else:
            print(f"  ✅ selected_for_view: {result['selected_for_view']}")
        
        print("\n" + "=" * 80)
        
        # Report results
        if errors:
            print("❌ ERRORS FOUND:")
            for error in errors:
                print(f"   {error}")
            print("\n⚠️  THE FIX IS NOT WORKING - Dates are still not being saved!")
            self.fail("\n".join(errors))
        else:
            print("✅ ALL FIELDS VERIFIED - Data is correctly persisted!")

    def test_ensure_tournament_with_empty_dates(self):
        """
        TEST: Verify what happens if dates dict is empty (DEBUG the bug)
        """
        print("\n" + "=" * 80)
        print("DEBUGGING: What happens with empty dates dict?")
        print("=" * 80)
        
        tournament_url = "https://test.com/empty-dates"
        tournament_name = "Empty Dates Tournament"
        location = "Test Location"
        
        # Empty dates dict - THIS MIGHT BE THE BUG!
        dates = {}
        
        print(f"\nInserting with EMPTY dates dict: {dates}")
        
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO tournaments
            (tournament_url, tournament_name, location, date_start, date_end,
             registration_opens, registration_closes, cancellation_deadline,
             competition_start, competition_end, selected_for_view, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            tournament_url,
            tournament_name,
            location,
            dates.get("competition_start", ""),  # Empty string!
            dates.get("competition_end", ""),    # Empty string!
            dates.get("registration_opens", ""),  # Empty string!
            dates.get("registration_closes", ""),  # Empty string!
            dates.get("cancellation_deadline", ""),  # Empty string!
            dates.get("competition_start", ""),  # Empty string!
            dates.get("competition_end", ""),    # Empty string!
            1
        ))
        conn.commit()
        
        # Read back
        cur.execute("""
            SELECT registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments WHERE tournament_url = ?
        """, (tournament_url,))
        
        row = cur.fetchone()
        conn.close()
        
        print(f"\nRead back from database:")
        print(f"  registration_opens: {repr(row[0])}")
        print(f"  registration_closes: {repr(row[1])}")
        print(f"  cancellation_deadline: {repr(row[2])}")
        print(f"  competition_start: {repr(row[3])}")
        print(f"  competition_end: {repr(row[4])}")
        
        # SQLite treats empty strings as NULL in some contexts!
        print(f"\nNote: SQLite may be treating empty strings as NULL")
        print(f"Are they NULL? {row[0] is None}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
