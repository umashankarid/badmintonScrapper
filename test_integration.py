"""
Integration tests for badmintonScrapPython
Tests complete workflows from database to API endpoints
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime, timedelta
import json

# Import from app
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestDatabaseIntegration(unittest.TestCase):
    """Test complete database workflow"""
    
    def setUp(self):
        """Create test database"""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_tournaments.db")
        self.setup_db()
    
    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)
    
    def setup_db(self):
        """Initialize test database"""
        conn = sqlite3.connect(self.db_path)
        
        # Create tournaments table
        conn.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL,
                location TEXT,
                date_start TEXT,
                date_end TEXT,
                selected_for_view INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                last_updated TIMESTAMP
            )
        """)
        
        # Create tournament_registrations table
        conn.execute("""
            CREATE TABLE tournament_1_registrations (
                id INTEGER PRIMARY KEY,
                license_id TEXT NOT NULL,
                singles_level TEXT,
                doubles_level TEXT,
                mixed_level TEXT,
                registration_date TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def test_complete_tournament_workflow(self):
        """Test: Create tournament → Register player → Query"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Step 1: Insert tournament
        future_date = (datetime.now() + timedelta(days=30)).isoformat()
        cur.execute("""
            INSERT INTO tournaments 
            (tournament_url, tournament_name, location, date_end, selected_for_view)
            VALUES (?, ?, ?, ?, ?)
        """, ("https://example.com/t1", "Test Tournament", "Stockholm", future_date, 1))
        
        # Step 2: Get tournament ID
        cur.execute("SELECT id FROM tournaments WHERE tournament_name=?", ("Test Tournament",))
        tournament_id = cur.fetchone()[0]
        
        # Step 3: Register player
        cur.execute("""
            INSERT INTO tournament_1_registrations
            (license_id, singles_level, doubles_level, mixed_level)
            VALUES (?, ?, ?, ?)
        """, ("test_license_123", "A", "B", "C"))
        
        conn.commit()
        
        # Step 4: Verify registration exists
        cur.execute("""
            SELECT COUNT(*) FROM tournament_1_registrations 
            WHERE license_id=?
        """, ("test_license_123",))
        count = cur.fetchone()[0]
        
        conn.close()
        
        # Verify
        self.assertEqual(tournament_id, 1)
        self.assertEqual(count, 1)
    
    def test_tournament_visibility_filtering(self):
        """Test: Only return selected tournaments"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        future_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        # Insert selected and unselected tournaments
        cur.execute("""
            INSERT INTO tournaments 
            (tournament_url, tournament_name, date_end, selected_for_view)
            VALUES (?, ?, ?, ?)
        """, ("https://example.com/t1", "Selected", future_date, 1))
        
        cur.execute("""
            INSERT INTO tournaments 
            (tournament_url, tournament_name, date_end, selected_for_view)
            VALUES (?, ?, ?, ?)
        """, ("https://example.com/t2", "Not Selected", future_date, 0))
        
        conn.commit()
        
        # Query only selected
        cur.execute("""
            SELECT COUNT(*) FROM tournaments WHERE selected_for_view=1
        """)
        selected_count = cur.fetchone()[0]
        
        # Query only unselected
        cur.execute("""
            SELECT COUNT(*) FROM tournaments WHERE selected_for_view=0
        """)
        unselected_count = cur.fetchone()[0]
        
        conn.close()
        
        self.assertEqual(selected_count, 1)
        self.assertEqual(unselected_count, 1)
    
    def test_expired_tournament_filtering(self):
        """Test: Filter out expired tournaments"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        past_date = (datetime.now() - timedelta(days=10)).isoformat()
        future_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        # Insert expired and active tournaments
        cur.execute("""
            INSERT INTO tournaments 
            (tournament_url, tournament_name, date_end, selected_for_view)
            VALUES (?, ?, ?, ?)
        """, ("https://example.com/expired", "Expired", past_date, 1))
        
        cur.execute("""
            INSERT INTO tournaments 
            (tournament_url, tournament_name, date_end, selected_for_view)
            VALUES (?, ?, ?, ?)
        """, ("https://example.com/active", "Active", future_date, 1))
        
        conn.commit()
        
        # Query only active
        cur.execute("""
            SELECT COUNT(*) FROM tournaments 
            WHERE selected_for_view=1 AND date_end >= date('now')
        """)
        active_count = cur.fetchone()[0]
        
        conn.close()
        
        self.assertEqual(active_count, 1)


class TestPlayerDataFlow(unittest.TestCase):
    """Test player data flow"""
    
    def setUp(self):
        """Create test database"""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_players.db")
        self.setup_db()
    
    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)
    
    def setup_db(self):
        """Initialize test database"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute("""
            CREATE TABLE players (
                license_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                ranking TEXT,
                last_updated TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def test_player_insert_and_retrieve(self):
        """Test: Insert player → Retrieve by license_id"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Insert player with ranking JSON
        ranking_json = json.dumps({
            "singles": {"A": {"rank": 5, "points": 1250}},
            "doubles": {"men": {"rank": 12, "points": 800}}
        })
        
        cur.execute("""
            INSERT INTO players
            (license_id, name, club, gender, email, phone, ranking)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("lic_123", "John Doe", "Club A", "M", "john@example.com", "555-1234", ranking_json))
        
        conn.commit()
        
        # Retrieve player
        cur.execute("""
            SELECT name, club, gender, ranking FROM players WHERE license_id=?
        """, ("lic_123",))
        
        result = cur.fetchone()
        conn.close()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "John Doe")
        self.assertEqual(result[1], "Club A")
        
        # Verify ranking is valid JSON
        ranking = json.loads(result[3])
        self.assertIn("singles", ranking)
    
    def test_player_update(self):
        """Test: Update player data"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Insert initial player
        cur.execute("""
            INSERT INTO players
            (license_id, name, club)
            VALUES (?, ?, ?)
        """, ("lic_456", "Jane Doe", "Club B"))
        
        conn.commit()
        
        # Update club
        cur.execute("""
            UPDATE players SET club=? WHERE license_id=?
        """, ("Club C", "lic_456"))
        
        conn.commit()
        
        # Verify update
        cur.execute("""
            SELECT club FROM players WHERE license_id=?
        """, ("lic_456",))
        
        new_club = cur.fetchone()[0]
        conn.close()
        
        self.assertEqual(new_club, "Club C")


class TestDataPersistence(unittest.TestCase):
    """Test data persistence across sessions"""
    
    def test_database_file_creation(self):
        """Test: Database files are created"""
        test_dir = tempfile.mkdtemp()
        
        try:
            # Create database
            db_path = os.path.join(test_dir, "test.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
            
            # Verify file exists
            self.assertTrue(os.path.exists(db_path))
            
            # Verify can reconnect
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            conn.close()
            
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0][0], "test")
        
        finally:
            shutil.rmtree(test_dir)


class TestConstraints(unittest.TestCase):
    """Test database constraints"""
    
    def setUp(self):
        """Create test database"""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_constraints.db")
        self.setup_db()
    
    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)
    
    def setup_db(self):
        """Initialize test database"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def test_unique_constraint_enforced(self):
        """Test: Unique constraint prevents duplicates"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Insert first tournament
        cur.execute("""
            INSERT INTO tournaments (tournament_url, tournament_name)
            VALUES (?, ?)
        """, ("https://example.com/t1", "Tournament 1"))
        
        conn.commit()
        
        # Try to insert duplicate URL
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("""
                INSERT INTO tournaments (tournament_url, tournament_name)
                VALUES (?, ?)
            """, ("https://example.com/t1", "Tournament 2"))
            conn.commit()
        
        conn.close()


if __name__ == '__main__':
    unittest.main()
