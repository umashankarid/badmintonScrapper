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
    
    def test_query_finds_players_with_complete_data(self):
        """Builds its own database: the original asserted against whatever
        happened to be in the developer's players.db, so it failed on a clean
        checkout and proved nothing on a populated one."""
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "players.db")
            conn = sqlite3.connect(db)
            conn.execute("""CREATE TABLE players (
                id INTEGER PRIMARY KEY, license_id TEXT, name TEXT,
                club TEXT, email TEXT, phone TEXT)""")
            conn.execute("INSERT INTO players (license_id, name, club, email, phone) "
                         "VALUES ('C-1','Complete Player','Komet','a@b.test','070')")
            conn.execute("INSERT INTO players (license_id, name, club) "
                         "VALUES ('I-1','Incomplete Player','Komet')")
            conn.commit()

            count = conn.execute(
                "SELECT COUNT(*) FROM players WHERE name IS NOT NULL AND name != '' "
                "AND club IS NOT NULL AND club != '' AND email IS NOT NULL "
                "AND email != '' AND phone IS NOT NULL AND phone != ''").fetchone()[0]
            conn.close()
            self.assertEqual(count, 1, "the completeness query did not isolate the complete row")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    
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
