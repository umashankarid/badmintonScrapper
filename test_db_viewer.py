"""
Unit tests for Database Viewer feature

Tests database viewing functionality:
- List all databases
- List tables in each database
- Get table contents
- Export table data
- Pagination for large tables
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import json
from datetime import datetime

class TestDatabaseViewer(unittest.TestCase):
    """Test database viewer functionality"""
    
    def setUp(self):
        """Create test databases with sample data"""
        self.test_dir = tempfile.mkdtemp()
        self.test_players_db = os.path.join(self.test_dir, "players.db")
        self.test_tournaments_db = os.path.join(self.test_dir, "tournaments.db")
        self.test_admin_db = os.path.join(self.test_dir, "admin.db")
        
        self.setup_test_databases()
    
    def tearDown(self):
        """Clean up test databases"""
        shutil.rmtree(self.test_dir)
    
    def setup_test_databases(self):
        """Initialize test databases with schema and data"""
        # Setup players.db
        conn = sqlite3.connect(self.test_players_db)
        conn.execute("""
            CREATE TABLE players (
                license_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                club TEXT,
                gender TEXT,
                email TEXT,
                ranking TEXT
            )
        """)
        conn.execute("""
            INSERT INTO players VALUES 
            ('lic_001', 'John Doe', 'Club A', 'M', 'john@example.com', '{"A": {"rank": 5}}')
        """)
        conn.commit()
        conn.close()
        
        # Setup tournaments.db
        conn = sqlite3.connect(self.test_tournaments_db)
        conn.execute("""
            CREATE TABLE tournaments (
                id INTEGER PRIMARY KEY,
                tournament_name TEXT NOT NULL,
                location TEXT,
                date_start TEXT,
                selected_for_view INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO tournaments VALUES
            (1, 'Test Tournament', 'Stockholm', '2026-08-20', 1)
        """)
        conn.execute("""
            CREATE TABLE tournament_1_registrations (
                id INTEGER PRIMARY KEY,
                license_id TEXT,
                singles_level TEXT
            )
        """)
        conn.execute("""
            INSERT INTO tournament_1_registrations VALUES
            (1, 'lic_001', 'A')
        """)
        conn.commit()
        conn.close()
        
        # Setup admin.db
        conn = sqlite3.connect(self.test_admin_db)
        conn.execute("""
            CREATE TABLE admin_users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        conn.execute("""
            INSERT INTO admin_users VALUES
            (1, 'admin', 'hashed_password')
        """)
        conn.commit()
        conn.close()
    
    def test_get_database_list(self):
        """Test: Get list of all databases"""
        # Expected databases
        dbs = ['players.db', 'tournaments.db', 'admin.db']
        
        # Verify files exist
        for db in dbs:
            db_path = os.path.join(self.test_dir, db)
            self.assertTrue(os.path.exists(db_path))
    
    def test_list_tables_in_database(self):
        """Test: List all tables in a database"""
        conn = sqlite3.connect(self.test_tournaments_db)
        cur = conn.cursor()
        
        # Get table list
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table'
            ORDER BY name
        """)
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        
        # Verify tables
        self.assertIn('tournaments', tables)
        self.assertIn('tournament_1_registrations', tables)
        self.assertEqual(len(tables), 2)
    
    def test_get_table_schema(self):
        """Test: Get table schema (columns and types)"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Get table info
        cur.execute("PRAGMA table_info(players)")
        columns = cur.fetchall()
        conn.close()
        
        # Verify columns
        self.assertEqual(len(columns), 6)
        col_names = [col[1] for col in columns]
        self.assertIn('license_id', col_names)
        self.assertIn('name', col_names)
    
    def test_get_table_contents(self):
        """Test: Get table contents with pagination"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Get data with limit
        limit = 10
        offset = 0
        cur.execute(f"""
            SELECT * FROM players
            LIMIT {limit} OFFSET {offset}
        """)
        rows = cur.fetchall()
        
        # Get total count
        cur.execute("SELECT COUNT(*) FROM players")
        total = cur.fetchone()[0]
        conn.close()
        
        # Verify
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0][0], 'lic_001')  # license_id
        self.assertEqual(rows[0][1], 'John Doe')  # name
    
    def test_get_table_row_count(self):
        """Test: Get row count for table"""
        conn = sqlite3.connect(self.test_tournaments_db)
        cur = conn.cursor()
        
        # Count registrations
        cur.execute("SELECT COUNT(*) FROM tournament_1_registrations")
        count = cur.fetchone()[0]
        conn.close()
        
        self.assertEqual(count, 1)
    
    def test_pagination_calculation(self):
        """Test: Calculate pagination details"""
        total_rows = 150
        page_size = 10
        current_page = 1
        
        # Calculate
        total_pages = (total_rows + page_size - 1) // page_size
        offset = (current_page - 1) * page_size
        
        # Verify
        self.assertEqual(total_pages, 15)
        self.assertEqual(offset, 0)
    
    def test_export_table_as_json(self):
        """Test: Export table data as JSON"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Get column names
        cur.execute("PRAGMA table_info(players)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Get data
        cur.execute("SELECT * FROM players")
        rows = cur.fetchall()
        conn.close()
        
        # Convert to JSON
        data = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            data.append(row_dict)
        
        json_str = json.dumps(data, indent=2)
        
        # Verify
        self.assertIn('lic_001', json_str)
        self.assertIn('John Doe', json_str)
    
    def test_export_table_as_csv(self):
        """Test: Export table data as CSV"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Get column names
        cur.execute("PRAGMA table_info(players)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Get data
        cur.execute("SELECT * FROM players")
        rows = cur.fetchall()
        conn.close()
        
        # Create CSV
        csv_lines = [','.join(columns)]
        for row in rows:
            csv_lines.append(','.join(str(val) if val else '' for val in row))
        
        csv_str = '\n'.join(csv_lines)
        
        # Verify
        self.assertIn('license_id', csv_str)
        self.assertIn('John Doe', csv_str)
    
    def test_handle_json_columns(self):
        """Test: Properly handle JSON data in columns"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Get ranking (JSON column)
        cur.execute("SELECT ranking FROM players WHERE license_id='lic_001'")
        ranking_json = cur.fetchone()[0]
        conn.close()
        
        # Parse JSON
        ranking = json.loads(ranking_json)
        
        # Verify
        self.assertIn('A', ranking)
        self.assertEqual(ranking['A']['rank'], 5)
    
    def test_database_file_verification(self):
        """Test: Verify database file exists and is readable"""
        # Verify file exists
        self.assertTrue(os.path.exists(self.test_players_db))
        
        # Verify can connect
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cur.fetchone()[0]
        conn.close()
        
        self.assertGreater(table_count, 0)
    
    def test_search_in_table(self):
        """Test: Search for specific values in table"""
        conn = sqlite3.connect(self.test_players_db)
        cur = conn.cursor()
        
        # Search by name
        search_term = 'John'
        cur.execute("""
            SELECT * FROM players 
            WHERE name LIKE ?
        """, (f'%{search_term}%',))
        
        results = cur.fetchall()
        conn.close()
        
        # Verify
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 'John Doe')


class TestDBViewerIntegration(unittest.TestCase):
    """Integration tests for database viewer"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)
    
    def test_multiple_tables_in_database(self):
        """Test: View multiple tables in single database"""
        db_path = os.path.join(self.test_dir, "test.db")
        conn = sqlite3.connect(db_path)
        
        # Create multiple tables
        conn.execute("CREATE TABLE table1 (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute("CREATE TABLE table2 (id INTEGER PRIMARY KEY, value INTEGER)")
        conn.execute("INSERT INTO table1 VALUES (1, 'test')")
        conn.execute("INSERT INTO table2 VALUES (1, 100)")
        conn.commit()
        
        # List tables
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table'
        """)
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        
        # Verify
        self.assertEqual(len(tables), 2)
        self.assertIn('table1', tables)
        self.assertIn('table2', tables)
    
    def test_dynamic_registration_tables(self):
        """Test: Handle dynamic tournament registration tables"""
        db_path = os.path.join(self.test_dir, "tournaments.db")
        conn = sqlite3.connect(db_path)
        
        # Create dynamic tables
        for tournament_id in range(1, 4):
            table_name = f"tournament_{tournament_id}_registrations"
            conn.execute(f"""
                CREATE TABLE {table_name} (
                    id INTEGER PRIMARY KEY,
                    license_id TEXT
                )
            """)
            conn.execute(f"INSERT INTO {table_name} VALUES (1, 'lic_001')")
        
        conn.commit()
        
        # List tables
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table'
            AND name LIKE 'tournament_%_registrations'
        """)
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        
        # Verify
        self.assertEqual(len(tables), 3)


if __name__ == '__main__':
    unittest.main()
