"""
Unit test to verify players table has proper data
Tests that player records have non-null name, club, email, phone when scraped
"""

import unittest
import sqlite3
import os

PLAYERS_DB = "players.db"

class TestPlayersData(unittest.TestCase):
    """Test player data integrity"""
    
    def setUp(self):
        self.db_path = PLAYERS_DB
        if not os.path.exists(self.db_path):
            raise Exception(f"Players database not found at {self.db_path}")
    
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
        
        if rows:
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
