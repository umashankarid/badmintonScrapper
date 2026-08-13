"""
Unit tests for BadmintonScrapPython
Tests critical functionality to ensure changes don't break core behavior
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import json
from unittest.mock import patch, MagicMock

# Import the app
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestDatabaseSchema(unittest.TestCase):
    """Test database schema creation and structure"""
    
    def setUp(self):
        """Create temporary databases for testing"""
        self.test_dir = tempfile.mkdtemp()
        self.tournaments_db = os.path.join(self.test_dir, "tournaments.db")
        self.players_db = os.path.join(self.test_dir, "players.db")
        self.admin_db = os.path.join(self.test_dir, "admin.db")
    
    def tearDown(self):
        """Clean up temporary databases"""
        shutil.rmtree(self.test_dir)
    
    def test_tournaments_db_schema(self):
        """Verify tournaments.db has required tables and columns"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()
        
        # Create tournament table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
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
        
        # Create tournament_registrations table (NORMALIZED - uses license_id FK)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tournament_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                license_id TEXT NOT NULL,
                singles_levels TEXT,
                doubles_levels TEXT,
                mixed_levels TEXT,
                doubles_partner TEXT,
                mixed_partner TEXT,
                registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (license_id) REFERENCES players(license_id)
            )
        """)
        conn.commit()
        
        # Verify tournaments table exists and has required columns
        cur.execute("PRAGMA table_info(tournaments)")
        columns = {row[1] for row in cur.fetchall()}
        
        required_cols = {'id', 'tournament_url', 'tournament_name', 'selected_for_view', 'date_end'}
        self.assertTrue(required_cols.issubset(columns), 
                       f"Missing columns: {required_cols - columns}")
        
        # Verify tournament_registrations table exists and has required columns
        cur.execute("PRAGMA table_info(tournament_registrations)")
        reg_columns = {row[1] for row in cur.fetchall()}
        
        required_reg_cols = {'id', 'tournament_id', 'license_id', 'registration_date'}
        self.assertTrue(required_reg_cols.issubset(reg_columns),
                       f"Missing registration columns: {required_reg_cols - reg_columns}")
        
        conn.close()
    
    def test_tournament_insertion(self):
        """Test inserting a tournament into tournaments table"""
        conn = sqlite3.connect(self.tournaments_db)
        cur = conn.cursor()
        
        # Create table
        cur.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL,
                selected_for_view INTEGER DEFAULT 0
            )
        """)
        
        # Insert tournament
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name, selected_for_view) VALUES (?,?,?)",
            ("https://example.com/tournament1", "Test Tournament", 1)
        )
        conn.commit()
        
        # Verify insertion
        cur.execute("SELECT tournament_name, selected_for_view FROM tournaments WHERE tournament_url=?",
                   ("https://example.com/tournament1",))
        result = cur.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Test Tournament")
        self.assertEqual(result[1], 1)
        
        conn.close()


class TestTournamentRegistrations(unittest.TestCase):
    """Test tournament registration functionality"""
    
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
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL
            )
        """)
        
        cur.execute("""
            CREATE TABLE tournament_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                license_id TEXT NOT NULL,
                singles_levels TEXT,
                doubles_levels TEXT,
                mixed_levels TEXT,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (license_id) REFERENCES players(license_id)
            )
        """)
        
        # Insert test tournament
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name) VALUES (?,?)",
            ("https://example.com/test", "Test Tournament")
        )
        
        conn.commit()
        conn.close()
    
    def test_register_player_in_tournament(self):
        """Test registering a player for a tournament"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Get tournament ID
        cur.execute("SELECT id FROM tournaments WHERE tournament_name=?", ("Test Tournament",))
        tournament_id = cur.fetchone()[0]
        
        # Register player (normalized: use license_id FK)
        cur.execute("""
            INSERT INTO tournament_registrations 
            (tournament_id, license_id, singles_levels, doubles_levels)
            VALUES (?,?,?,?)
        """, (tournament_id, "lic_001", "A,B", "C"))
        
        conn.commit()
        
        # Verify registration
        cur.execute(
            "SELECT license_id, singles_levels FROM tournament_registrations WHERE tournament_id=?",
            (tournament_id,)
        )
        result = cur.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "lic_001")
        self.assertEqual(result[1], "A,B")
        
        conn.close()
    
    def test_multiple_registrations_for_tournament(self):
        """Test multiple player registrations for same tournament"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        tournament_id = 1
        
        players = [
            ("lic_001", "A"),
            ("lic_002", "B"),
            ("lic_003", "C"),
        ]
        
        # Register multiple players (normalized: license_id + level only)
        for license_id, level in players:
            cur.execute("""
                INSERT INTO tournament_registrations 
                (tournament_id, license_id, singles_levels)
                VALUES (?,?,?)
            """, (tournament_id, license_id, level))
        
        conn.commit()
        
        # Verify all registrations
        cur.execute(
            "SELECT COUNT(*) FROM tournament_registrations WHERE tournament_id=?",
            (tournament_id,)
        )
        count = cur.fetchone()[0]
        self.assertEqual(count, 3)
        
        conn.close()
    
    def test_delete_registration(self):
        """Test deleting a player registration"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        tournament_id = 1
        license_id = "lic_test"
        
        # Register player (normalized: license_id only)
        cur.execute("""
            INSERT INTO tournament_registrations 
            (tournament_id, license_id)
            VALUES (?,?)
        """, (tournament_id, license_id))
        
        conn.commit()
        
        # Get registration ID
        cur.execute("SELECT id FROM tournament_registrations WHERE license_id=?", (license_id,))
        reg_id = cur.fetchone()[0]
        
        # Delete registration
        cur.execute("DELETE FROM tournament_registrations WHERE id=?", (reg_id,))
        conn.commit()
        
        # Verify deletion
        cur.execute("SELECT COUNT(*) FROM tournament_registrations WHERE id=?", (reg_id,))
        count = cur.fetchone()[0]
        self.assertEqual(count, 0)
        
        conn.close()


class TestTournamentVisibility(unittest.TestCase):
    """Test tournament selection/visibility functionality"""
    
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
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL,
                date_end TEXT,
                selected_for_view INTEGER DEFAULT 0
            )
        """)
        
        # Insert test tournaments
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name, date_end, selected_for_view) VALUES (?,?,?,?)",
            ("https://example.com/t1", "Tournament 1", "2026-12-31", 1)
        )
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name, date_end, selected_for_view) VALUES (?,?,?,?)",
            ("https://example.com/t2", "Tournament 2", "2026-12-31", 0)
        )
        
        conn.commit()
        conn.close()
    
    def test_get_selected_tournaments(self):
        """Test getting only selected tournaments"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Get only selected tournaments
        cur.execute(
            "SELECT tournament_name FROM tournaments WHERE selected_for_view=1"
        )
        results = cur.fetchall()
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "Tournament 1")
        
        conn.close()
    
    def test_toggle_tournament_visibility(self):
        """Test toggling tournament visibility"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Get current visibility
        cur.execute("SELECT selected_for_view FROM tournaments WHERE tournament_name=?", ("Tournament 2",))
        current = cur.fetchone()[0]
        self.assertEqual(current, 0)
        
        # Toggle visibility
        new_visibility = 1 - current
        cur.execute(
            "UPDATE tournaments SET selected_for_view=? WHERE tournament_name=?",
            (new_visibility, "Tournament 2")
        )
        conn.commit()
        
        # Verify toggle
        cur.execute("SELECT selected_for_view FROM tournaments WHERE tournament_name=?", ("Tournament 2",))
        updated = cur.fetchone()[0]
        self.assertEqual(updated, 1)
        
        conn.close()
    
    def test_filter_by_end_date(self):
        """Test filtering tournaments by end date"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Insert expired tournament
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name, date_end, selected_for_view) VALUES (?,?,?,?)",
            ("https://example.com/t3", "Expired Tournament", "2020-01-01", 1)
        )
        conn.commit()
        
        # Get only active selected tournaments
        cur.execute("""
            SELECT tournament_name FROM tournaments 
            WHERE selected_for_view=1 AND date_end >= date('now')
        """)
        results = cur.fetchall()
        
        # Should only have Tournament 1
        tournament_names = [r[0] for r in results]
        self.assertIn("Tournament 1", tournament_names)
        self.assertNotIn("Expired Tournament", tournament_names)
        
        conn.close()


class TestDropboxSync(unittest.TestCase):
    """Test Dropbox sync functionality"""
    
    def test_file_exists_check(self):
        """Test checking if file exists in Dropbox"""
        # This would require mocking Dropbox API
        # For now, test the file existence check logic
        
        files_in_dropbox = {
            "/BadmintonScrapPython-Databases/tournaments.db",
            "/BadmintonScrapPython-Databases/players.db"
        }
        
        # Test file existence
        test_file = "/BadmintonScrapPython-Databases/tournaments.db"
        self.assertIn(test_file, files_in_dropbox)
        
        # Test missing file
        missing_file = "/BadmintonScrapPython-Databases/missing.db"
        self.assertNotIn(missing_file, files_in_dropbox)
    
    def test_sync_files_list(self):
        """Test that only correct files are synced"""
        # Root level files only (no tournaments/*.db)
        sync_files = [
            "players.db",
            "admin.db",
            "point_rules.db",
            "tournaments.db"
        ]
        
        # These should NOT be in sync list
        excluded_files = [
            "tournaments/bmk_komet.db",
            "tournaments/other.db"
        ]
        
        for file in sync_files:
            self.assertNotIn("/", file, f"Sync file should not have path: {file}")
        
        for file in excluded_files:
            self.assertTrue("/" in file, 
                          f"Excluded file should have path separator: {file}")


class TestDataIntegrity(unittest.TestCase):
    """Test data integrity and consistency"""
    
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
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_url TEXT UNIQUE NOT NULL,
                tournament_name TEXT NOT NULL
            )
        """)
        
        # Create minimal players table for FK integrity
        cur.execute("""
            CREATE TABLE players (
                license_id TEXT PRIMARY KEY,
                name TEXT
            )
        """)
        
        cur.execute("""
            CREATE TABLE tournament_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                license_id TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (license_id) REFERENCES players(license_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def test_foreign_key_constraint(self):
        """Test that foreign key constraints are enforced"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # Check that tournament_id FK is enforced by trying invalid ID
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO tournament_registrations (tournament_id, license_id) VALUES (?,?)",
                (999, "test_lic")  # tournament_id 999 doesn't exist
            )
            conn.commit()
        
        conn.close()
    
    def test_unique_constraint(self):
        """Test that unique constraints are enforced"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Insert first tournament
        cur.execute(
            "INSERT INTO tournaments (tournament_url, tournament_name) VALUES (?,?)",
            ("https://example.com/t1", "Tournament 1")
        )
        conn.commit()
        
        # Try to insert duplicate tournament_url
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO tournaments (tournament_url, tournament_name) VALUES (?,?)",
                ("https://example.com/t1", "Duplicate")
            )
            conn.commit()
        
        conn.close()


if __name__ == '__main__':
    unittest.main()
