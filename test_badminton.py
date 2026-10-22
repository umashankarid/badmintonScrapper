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


# Page 2 of the find listing: repeats page-1 rows (BWF accumulates) and adds one
# more tournament further away, mirroring the real pagination behaviour.
_FIND_RESULTS_PAGE2_HTML = """
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
  <li class="list__item">
    <a class="media__link" href="/find?id=33333333-3333-3333-3333-333333333333">Far Away Open 2026</a>
    <div class="media__subheading"><span class="nav-link__value">Luleå</span></div>
    <time datetime="2026-12-05T00:00:00"></time>
  </li>
</ul>
"""


class TestEventClassification(unittest.TestCase):
    """Tests for _classify_bwf_events (Swedish vs English event codes)."""

    def _classify(self, event_names):
        import app
        from bs4 import BeautifulSoup
        html = "<div>" + "".join(
            f'<a href="/sport/event.aspx?id=x&event={i}">{n}</a>'
            for i, n in enumerate(event_names)
        ) + "</div>"
        return app._classify_bwf_events(BeautifulSoup(html, "html.parser"))

    def test_swedish_scheme(self):
        """HS/DS=singles, HD/DD=doubles, MD=mixed (Swedish 'Mixed Dubbel')."""
        cats = self._classify(["HS A", "DS A", "HD B", "DD B", "MD Elit"])
        self.assertEqual(cats["singles_levels"], ["DS A", "HS A"])
        self.assertEqual(cats["doubles_levels"], ["DD B", "HD B"])
        self.assertEqual(cats["mixed_levels"], ["MD Elit"])

    def test_english_scheme_youth(self):
        """MS/WS=singles, MD/WD=doubles, XD=mixed (English). Regression for
        'Swedish Youth Games 2026 U13-15' where Singles/Doubles were empty."""
        cats = self._classify(["MS U13", "WS U13", "XD U13", "MD U13", "WD U13"])
        self.assertEqual(sorted(cats["singles_levels"]), ["MS U13", "WS U13"])
        self.assertEqual(sorted(cats["doubles_levels"]), ["MD U13", "WD U13"])
        self.assertEqual(cats["mixed_levels"], ["XD U13"])
        # Singles and doubles must NOT be empty for this tournament.
        self.assertTrue(cats["singles_levels"])
        self.assertTrue(cats["doubles_levels"])

    def test_md_disambiguation(self):
        """'MD' is Men's Doubles when English codes are present, else Mixed."""
        english = self._classify(["MS U15", "MD U15"])   # MS present -> English
        self.assertIn("MD U15", english["doubles_levels"])
        self.assertEqual(english["mixed_levels"], [])
        swedish = self._classify(["HS A", "MD A"])        # no English-only code
        self.assertIn("MD A", swedish["mixed_levels"])
        self.assertEqual(swedish["doubles_levels"], [])

    def test_partners_set_when_doubles_present(self):
        cats = self._classify(["WD U13"])
        self.assertTrue(cats["doubles_partner"])


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

    def test_scrape_tournaments_paginates(self):
        """Walks all result pages and deduplicates by id.

        The find listing is paginated (~20/page) and accumulates, so a tournament
        only appearing on page 2 must still be returned (regression for a player
        whose tournament was on page 2 and was missed when only page 1 was read).
        """
        import app

        def _get(url, *args, **kwargs):
            return _FakeResp("<form id='form_globalsearch'></form>")

        def _post(url, *args, **kwargs):
            page = str((kwargs.get("data") or {}).get("Page", "1"))
            if page == "1":
                return _FakeResp(_FIND_RESULTS_HTML)        # 2 tournaments
            return _FakeResp(_FIND_RESULTS_PAGE2_HTML)        # same 2 + 1 new

        sess = MagicMock()
        sess.get.side_effect = _get
        sess.post.side_effect = _post

        results = app.scrape_bwf_tournaments_in_range("2026-11-01", "2026-12-13", s=sess)
        ids = [t["id"] for t in results]
        # Page-2-only tournament must be present, and no duplicates.
        self.assertIn("33333333-3333-3333-3333-333333333333", ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(results), 3)

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


# HTML fragment mimicking a Badminton Sweden player-profile /tournaments/<year> page.
_PROFILE_TOURNAMENTS_HTML = """
<ul>
  <li class="list__item">
    <time datetime="2026-10-03T00:00:00"></time>
    <a href="/sport/tournament?id=6E816720-F05B-4046-9AE7-043D9E2DDD3F">Kometsträffen 2026</a>
  </li>
  <li class="list__item">
    <time datetime="2026-09-26T00:00:00"></time>
    <a href="/sport/tournament?id=E552771A-AC8E-419F-9E50-AFCBC548E3C4">Kometslaget 2026</a>
  </li>
</ul>
"""


class TestPlayerPayments(unittest.TestCase):
    """Tests for the 'Payment to club' feature (payments.db + endpoints)."""

    def setUp(self):
        import app
        # Isolate the payments DB to a temp file per test.
        self._dir = tempfile.mkdtemp()
        self._orig_db = app.PAYMENTS_DB
        app.PAYMENTS_DB = os.path.join(self._dir, "payments.db")
        app.init_payments_db()
        self.app = app
        self.client = app.app.test_client()

    def tearDown(self):
        self.app.PAYMENTS_DB = self._orig_db
        shutil.rmtree(self._dir)

    def _login_as(self, name, admin=False, license_id="IID05778873"):
        with self.client.session_transaction() as sess:
            sess["bwf_player"] = name
            sess["bwf_license_id"] = license_id
            sess["admin"] = admin
            sess["bwf_profile_url"] = "/player-profile/58036C5F-1B9B-4873-BF3B-190C890191F6"

    # --- access gating ---------------------------------------------------
    def test_feature_allowed_only_for_aadvika(self):
        self.assertTrue(self.app._payment_feature_allowed("Aadvika Umashankar"))
        self.assertTrue(self.app._payment_feature_allowed("aadvika  umashankar"))
        self.assertFalse(self.app._payment_feature_allowed("Someone Else"))
        self.assertFalse(self.app._payment_feature_allowed(""))

    def test_get_payments_blocked_for_other_player(self):
        self._login_as("Someone Else", license_id="IID00000000")
        resp = self.client.get("/api/player-payments")
        data = resp.get_json()
        self.assertFalse(data["allowed"])

    def test_get_payments_blocked_when_logged_out(self):
        resp = self.client.get("/api/player-payments")
        self.assertEqual(resp.status_code, 401)

    # --- custom items ----------------------------------------------------
    def test_add_and_list_custom_item(self):
        self._login_as("Aadvika Umashankar")
        resp = self.client.post("/api/player-payments", json={
            "item_name": "Bus booking to Uppsala", "amount": 150, "item_date": "2026-11-02",
            "notes": "Return trip"
        })
        self.assertTrue(resp.get_json()["success"])

        data = self.client.get("/api/player-payments").get_json()
        self.assertTrue(data["allowed"])
        self.assertEqual(len(data["payments"]), 1)
        item = data["payments"][0]
        self.assertEqual(item["item_name"], "Bus booking to Uppsala")
        self.assertEqual(item["item_type"], "custom")
        self.assertEqual(item["amount"], 150)
        self.assertEqual(item["paid"], 0)
        self.assertEqual(data["summary"]["unpaid_amount"], 150)

    def test_toggle_paid(self):
        self._login_as("Aadvika Umashankar")
        self.client.post("/api/player-payments", json={"item_name": "Club fee", "amount": 100})
        pid = self.client.get("/api/player-payments").get_json()["payments"][0]["id"]

        self.client.post("/api/player-payments/toggle-paid", json={"id": pid})
        data = self.client.get("/api/player-payments").get_json()
        self.assertEqual(data["payments"][0]["paid"], 1)
        self.assertEqual(data["summary"]["paid_amount"], 100)
        self.assertEqual(data["summary"]["unpaid_amount"], 0)

        # toggling again flips back to unpaid
        self.client.post("/api/player-payments/toggle-paid", json={"id": pid})
        data = self.client.get("/api/player-payments").get_json()
        self.assertEqual(data["payments"][0]["paid"], 0)

    def test_delete_item(self):
        self._login_as("Aadvika Umashankar")
        self.client.post("/api/player-payments", json={"item_name": "Mistake", "amount": 1})
        pid = self.client.get("/api/player-payments").get_json()["payments"][0]["id"]
        self.client.delete(f"/api/player-payments/{pid}")
        data = self.client.get("/api/player-payments").get_json()
        self.assertEqual(len(data["payments"]), 0)

    def test_player_cannot_touch_others_items(self):
        # Aadvika creates an item...
        self._login_as("Aadvika Umashankar", license_id="IID05778873")
        self.client.post("/api/player-payments", json={"item_name": "Private", "amount": 5})
        pid = self.client.get("/api/player-payments").get_json()["payments"][0]["id"]
        # ...a different allowed session with a different license must not delete it.
        with self.client.session_transaction() as sess:
            sess["bwf_player"] = "Aadvika Umashankar"
            sess["bwf_license_id"] = "IID99999999"
            sess["admin"] = False
        resp = self.client.delete(f"/api/player-payments/{pid}")
        self.assertFalse(resp.get_json().get("success", False))

    # --- tournament history scraping + sync ------------------------------
    def test_scrape_history(self):
        def _get(url, *a, **k):
            return _FakeResp(_PROFILE_TOURNAMENTS_HTML)
        sess = MagicMock(); sess.get.side_effect = _get
        hist = self.app.scrape_player_tournament_history(
            "/player-profile/58036C5F-1B9B-4873-BF3B-190C890191F6", 2026, s=sess)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["id"], "6E816720-F05B-4046-9AE7-043D9E2DDD3F")
        self.assertEqual(hist[0]["name"], "Kometsträffen 2026")
        self.assertEqual(hist[0]["date"], "2026-10-03")

    def test_sync_adds_tournaments_without_duplicates(self):
        self._login_as("Aadvika Umashankar")

        def _get(url, *a, **k):
            return _FakeResp(_PROFILE_TOURNAMENTS_HTML)
        sess = MagicMock(); sess.get.side_effect = _get

        with patch.object(self.app, "_bwf_session", return_value=sess):
            r1 = self.client.post("/api/player-payments/sync").get_json()
        self.assertTrue(r1["success"])
        self.assertEqual(r1["added"], 2)

        data = self.client.get("/api/player-payments").get_json()
        self.assertEqual(len(data["payments"]), 2)
        self.assertTrue(all(p["item_type"] == "tournament" for p in data["payments"]))

        # Running sync again must not duplicate (source_key dedup).
        with patch.object(self.app, "_bwf_session", return_value=sess):
            r2 = self.client.post("/api/player-payments/sync").get_json()
        self.assertEqual(r2["added"], 0)
        data = self.client.get("/api/player-payments").get_json()
        self.assertEqual(len(data["payments"]), 2)

    def test_auto_sync_history_only_on_first_run(self):
        """First sync scrapes history (last 6 months); once any row exists, history
        is never scraped again — only new upcoming tournaments are added."""
        scrape_calls = []

        def fake_history(profile_url, year, s=None):
            scrape_calls.append(year)
            return [{"id": "AAAAAAAA-0000-0000-0000-000000000000",
                     "name": "Old Tournament", "date": None}]

        with patch.object(self.app, "scrape_player_tournament_history", side_effect=fake_history), \
             patch.object(self.app, "find_my_bwf_tournaments", return_value=[]), \
             patch.object(self.app, "_bwf_session", return_value=MagicMock()):
            added1, _ = self.app._auto_sync_payments("Aadvika Umashankar", "IID05778873", "/player-profile/x")
            self.assertEqual(added1, 1)
            self.assertTrue(len(scrape_calls) >= 1)   # history scraped on first run

            scrape_calls.clear()
            added2, _ = self.app._auto_sync_payments("Aadvika Umashankar", "IID05778873", "/player-profile/x")
            self.assertEqual(added2, 0)
            self.assertEqual(scrape_calls, [])        # history NOT scraped again

    def test_auto_sync_history_filters_to_last_6_months(self):
        """History entries older than ~6 months are excluded on the first sync."""
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        old = (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d")

        def fake_history(profile_url, year, s=None):
            return [
                {"id": "11111111-0000-0000-0000-000000000000", "name": "Recent", "date": recent},
                {"id": "22222222-0000-0000-0000-000000000000", "name": "TooOld", "date": old},
            ]

        with patch.object(self.app, "scrape_player_tournament_history", side_effect=fake_history), \
             patch.object(self.app, "find_my_bwf_tournaments", return_value=[]), \
             patch.object(self.app, "_bwf_session", return_value=MagicMock()):
            self.app._auto_sync_payments("Aadvika Umashankar", "IID05778873", "/player-profile/x")

        self._login_as("Aadvika Umashankar")
        names = [p["item_name"] for p in self.client.get("/api/player-payments").get_json()["payments"]]
        self.assertIn("Recent", names)
        self.assertNotIn("TooOld", names)

    def test_sync_never_overrides_paid_status(self):
        """Re-syncing a tournament already marked paid must not reset paid/paid_date."""
        self._login_as("Aadvika Umashankar")

        def fake_history(profile_url, year, s=None):
            return [{"id": "33333333-0000-0000-0000-000000000000",
                     "name": "Paid Tournament", "date": None}]

        # First sync seeds the tournament.
        with patch.object(self.app, "scrape_player_tournament_history", side_effect=fake_history), \
             patch.object(self.app, "find_my_bwf_tournaments", return_value=[]), \
             patch.object(self.app, "_bwf_session", return_value=MagicMock()):
            self.app._auto_sync_payments("Aadvika Umashankar", "IID05778873", "/player-profile/x")

        pid = self.client.get("/api/player-payments").get_json()["payments"][0]["id"]
        self.client.post("/api/player-payments/toggle-paid", json={"id": pid})  # mark paid
        before = self.client.get("/api/player-payments").get_json()["payments"][0]
        self.assertEqual(before["paid"], 1)

        # Sync again (history is now skipped, but even via the endpoint the row must survive).
        with patch.object(self.app, "scrape_player_tournament_history", side_effect=fake_history), \
             patch.object(self.app, "find_my_bwf_tournaments", return_value=[]), \
             patch.object(self.app, "_bwf_session", return_value=MagicMock()):
            self.app._auto_sync_payments("Aadvika Umashankar", "IID05778873", "/player-profile/x")

        after = self.client.get("/api/player-payments").get_json()["payments"][0]
        self.assertEqual(after["paid"], 1)
        self.assertEqual(after["paid_date"], before["paid_date"])
        self.assertEqual(after["id"], pid)   # same row, not re-inserted


if __name__ == '__main__':
    unittest.main()
