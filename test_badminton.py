"""
Unit tests for BadmintonScrapPython
Tests critical functionality to ensure changes don't break core behavior
"""

import unittest
import sqlite3
import os

# Prevent recursion: importing app runs an import-time test gate that
# re-discovers this file. Setting this before any `import app` disables that
# gate during test runs (the gate still runs on real app startup).
os.environ["SKIP_STARTUP_TESTS"] = "1"

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
        cur.execute("SELECT tournament_name FROM tournaments WHERE tournament_name=?", ("Test Tournament",))
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


# Sample HTML fragments mimicking Badminton Sweden responses, used to test the
# "My BWF tournaments" scraping helpers without hitting the network.
_FIND_RESULTS_HTML = """
<ul>
  <li class="list__item">
    <a class="media__link" href="/find?id=1AA58719-CD58-45C6-916C-59B599563DC0">Distriktsmästerskap 2026 Stockholm</a>
    <div class="media__subheading"><span class="nav-link__value">Stockholm</span></div>
    <time datetime="2026-11-15T00:00:00"></time>
    <time datetime="2026-11-16T00:00:00"></time>
  </li>
  <li class="list__item">
    <a class="media__link" href="/find?id=22222222-2222-2222-2222-222222222222">Other Cup 2026</a>
    <div class="media__subheading"><span class="nav-link__value">Göteborg</span></div>
    <time datetime="2026-12-01T00:00:00"></time>
  </li>
</ul>
"""

_PLAYERS_CONTENT_HTML = """
<ul>
  <li class="list__item">
    <a href="/sport/player.aspx?id=1aa58719&player=4">Ahlgren, Tomas</a>
  </li>
  <li class="list__item">
    <a href="/sport/player.aspx?id=1aa58719&player=6">Beriwal, Aahaan</a>
  </li>
</ul>
"""

_PLAYER_PAGE_HTML = """
<div>
  <a href="/sport/events.aspx?id=1aa58719">Klasser</a>
  <a href="/sport/event.aspx?id=1aa58719&event=3">HD Senior med Anton Tjulin</a>
  <a href="/sport/event.aspx?id=1aa58719&event=5">MD Senior med Cecilia Narfors</a>
</div>
"""


class _FakeResp:
    def __init__(self, text):
        self.text = text


class TestMyBwfTournaments(unittest.TestCase):
    """Tests for the 'My BWF tournaments' scraping helpers and endpoint."""

    def _fake_session(self, players_html=_PLAYERS_CONTENT_HTML, player_html=_PLAYER_PAGE_HTML):
        """Build a MagicMock requests session returning canned BWF responses."""
        sess = MagicMock()

        def _get(url, *args, **kwargs):
            if "GetPlayersContent" in url:
                return _FakeResp(players_html)
            if "player.aspx" in url:
                return _FakeResp(player_html)
            if "/find" in url:
                return _FakeResp("<form id='form_globalsearch'></form>")
            return _FakeResp("")

        def _post(url, *args, **kwargs):
            if "DoSearch" in url:
                return _FakeResp(_FIND_RESULTS_HTML)
            return _FakeResp("")

        sess.get.side_effect = _get
        sess.post.side_effect = _post
        return sess

    def test_scrape_tournaments_in_range(self):
        """Parses tournament id/name/location/dates from the find listing."""
        import app
        sess = self._fake_session()
        results = app.scrape_bwf_tournaments_in_range("2026-11-01", "2026-12-13", s=sess)
        self.assertEqual(len(results), 2)
        first = results[0]
        self.assertEqual(first["id"], "1AA58719-CD58-45C6-916C-59B599563DC0")
        self.assertEqual(first["name"], "Distriktsmästerskap 2026 Stockholm")
        self.assertEqual(first["location"], "Stockholm")
        self.assertEqual(first["date_start"], "2026-11-15")
        self.assertEqual(first["date_end"], "2026-11-16")
        self.assertIn("/tournament/1AA58719-CD58-45C6-916C-59B599563DC0", first["url"])

    def test_player_entry_match_found(self):
        """Finds a matching player and extracts their categories (partner stripped)."""
        import app
        sess = self._fake_session()
        entry = app.scrape_bwf_tournament_player_entry("1aa58719", "Tomas Ahlgren", s=sess)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["categories"], ["HD Senior", "MD Senior"])

    def test_player_entry_match_lastname_first(self):
        """Matching works when the session name is 'Lastname, Firstname' too."""
        import app
        sess = self._fake_session()
        entry = app.scrape_bwf_tournament_player_entry("1aa58719", "Ahlgren, Tomas", s=sess)
        self.assertIsNotNone(entry)

    def test_player_entry_no_match(self):
        """Returns None when the player is not in the tournament's list."""
        import app
        sess = self._fake_session()
        entry = app.scrape_bwf_tournament_player_entry("1aa58719", "Nonexistent Person", s=sess)
        self.assertIsNone(entry)

    def test_endpoint_requires_player_login(self):
        """Endpoint returns empty list when not logged in as a player."""
        import app
        client = app.app.test_client()
        resp = client.get("/api/my-bwf-tournaments")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["tournaments"], [])

    def test_endpoint_admin_gets_empty(self):
        """Admins don't get the player-specific list."""
        import app
        client = app.app.test_client()
        with client.session_transaction() as sess:
            sess["bwf_player"] = "Some Admin"
            sess["admin"] = True
        resp = client.get("/api/my-bwf-tournaments")
        data = resp.get_json()
        self.assertEqual(data["tournaments"], [])

    def test_endpoint_player_returns_matches(self):
        """Logged-in player gets their matched tournaments with categories."""
        import app
        # Clear cache so the stub is exercised
        app._MY_BWF_CACHE.clear()
        client = app.app.test_client()
        with client.session_transaction() as sess:
            sess["bwf_player"] = "Tomas Ahlgren"
            sess["admin"] = False

        with patch.object(app, "_bwf_session", return_value=self._fake_session()):
            resp = client.get("/api/my-bwf-tournaments")
        data = resp.get_json()
        self.assertTrue(data["success"])
        # Both tournaments use the same canned player list, so both match.
        self.assertEqual(len(data["tournaments"]), 2)
        self.assertEqual(data["tournaments"][0]["categories"], ["HD Senior", "MD Senior"])
        self.assertIn("url", data["tournaments"][0])


if __name__ == '__main__':
    unittest.main()
