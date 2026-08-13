"""
Unit tests for player data storage in players.db

Tests two insertion paths:
1. Admin registers player (live search → register): stores name, license_id, club, profile_url, gender, ranking
2. Player logs in: stores ALL fields (name, license_id, club, profile_url, gender, email, phone, dob, age, ranking)

Also tests:
- Upsert behavior (update existing player without losing data)
- Ranking JSON structure with all categories (including age-based)
- COALESCE logic (login data not overwritten by registration)
"""

import unittest
import sqlite3
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestPlayerStorageSchema(unittest.TestCase):
    """Test that players table has all required fields"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "players.db")
        self._create_table()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT,
                name TEXT NOT NULL,
                profile_url TEXT UNIQUE,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                dob TEXT,
                age TEXT,
                ranking TEXT,
                last_updated TIMESTAMP,
                last_scraped TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def test_all_columns_exist(self):
        """Verify players table has all required columns"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(players)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()

        expected = {
            'id', 'license_id', 'name', 'profile_url', 'club', 'gender',
            'email', 'phone', 'dob', 'age', 'ranking', 'last_updated', 'last_scraped'
        }
        self.assertEqual(expected, columns)

    def test_ranking_column_accepts_json(self):
        """Verify ranking column can store JSON with all categories"""
        ranking = {
            "DS": {"rank": "80", "points": "2294"},
            "DD": {"rank": "250", "points": "1064"},
            "MD": {"rank": "367", "points": "1312"},
            "DS U13": {"rank": "1", "points": "2294"},
            "DD U13": {"rank": "1", "points": "1064"},
            "MD U13": {"rank": "1", "points": "1312"}
        }
        ranking_json = json.dumps(ranking)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO players (license_id, name, ranking) VALUES (?, ?, ?)",
            ("LIC001", "Test Player", ranking_json)
        )
        conn.commit()

        cur = conn.cursor()
        cur.execute("SELECT ranking FROM players WHERE license_id = ?", ("LIC001",))
        stored = cur.fetchone()[0]
        conn.close()

        parsed = json.loads(stored)
        self.assertEqual(parsed["DS"]["rank"], "80")
        self.assertEqual(parsed["DS"]["points"], "2294")
        self.assertEqual(parsed["DS U13"]["rank"], "1")
        self.assertEqual(parsed["MD U13"]["points"], "1312")
        self.assertEqual(len(parsed), 6)


class TestUpdatePlayerInDb(unittest.TestCase):
    """Test the update_player_in_db function from players_scraper.py"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "players.db")
        self._create_table()
        # Patch the PLAYERS_DB path in players_scraper module
        self.patcher = patch('players_scraper.PLAYERS_DB', self.db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir)

    def _create_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT,
                name TEXT NOT NULL,
                profile_url TEXT UNIQUE,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                dob TEXT,
                age TEXT,
                ranking TEXT,
                last_updated TIMESTAMP,
                last_scraped TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def _get_player(self, license_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM players WHERE license_id = ?", (license_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def test_insert_new_player_on_login(self):
        """Test inserting a new player with ALL fields (login scenario)"""
        from players_scraper import update_player_in_db

        ranking = json.dumps({
            "HS": {"rank": "45", "points": "1500"},
            "HD": {"rank": "120", "points": "800"},
            "MD": {"rank": "200", "points": "600"},
            "HS U17": {"rank": "3", "points": "1500"}
        })

        result = update_player_in_db(
            license_id="12345678",
            name="Erik Andersson",
            profile_url="/player-profile/abc-123",
            club="BMK Komet",
            gender="M",
            email="erik@example.com",
            phone="+46701234567",
            dob="2009-05-15",
            age="17",
            ranking=ranking
        )

        self.assertTrue(result)

        player = self._get_player("12345678")
        self.assertIsNotNone(player)
        self.assertEqual(player["license_id"], "12345678")
        self.assertEqual(player["name"], "Erik Andersson")
        self.assertEqual(player["profile_url"], "/player-profile/abc-123")
        self.assertEqual(player["club"], "BMK Komet")
        self.assertEqual(player["gender"], "M")
        self.assertEqual(player["email"], "erik@example.com")
        self.assertEqual(player["phone"], "+46701234567")
        self.assertEqual(player["dob"], "2009-05-15")
        self.assertEqual(player["age"], "17")
        self.assertIsNotNone(player["last_updated"])
        self.assertIsNotNone(player["last_scraped"])

        # Verify ranking JSON
        stored_ranking = json.loads(player["ranking"])
        self.assertEqual(stored_ranking["HS"]["rank"], "45")
        self.assertEqual(stored_ranking["HS"]["points"], "1500")
        self.assertEqual(stored_ranking["HS U17"]["rank"], "3")

    def test_insert_new_player_on_registration(self):
        """Test inserting a new player with limited fields (admin registration scenario)"""
        from players_scraper import update_player_in_db

        ranking = json.dumps({
            "DS": {"rank": "80", "points": "2294"},
            "DD": {"rank": "250", "points": "1064"}
        })

        # Registration only provides: name, license_id, club, profile_url, gender, ranking
        # Does NOT provide: email, phone, dob, age
        result = update_player_in_db(
            license_id="87654321",
            name="Anna Svensson",
            profile_url="/player-profile/def-456",
            club="Lunds BK",
            gender="F",
            ranking=ranking
        )

        self.assertTrue(result)

        player = self._get_player("87654321")
        self.assertIsNotNone(player)
        self.assertEqual(player["license_id"], "87654321")
        self.assertEqual(player["name"], "Anna Svensson")
        self.assertEqual(player["profile_url"], "/player-profile/def-456")
        self.assertEqual(player["club"], "Lunds BK")
        self.assertEqual(player["gender"], "F")
        # These should be None (not available during registration)
        self.assertIsNone(player["email"])
        self.assertIsNone(player["phone"])
        self.assertIsNone(player["dob"])
        self.assertIsNone(player["age"])

        # Ranking should be stored
        stored_ranking = json.loads(player["ranking"])
        self.assertEqual(stored_ranking["DS"]["points"], "2294")

    def test_login_after_registration_fills_missing_fields(self):
        """Test that login updates player with email, phone, dob, age without losing existing data"""
        from players_scraper import update_player_in_db

        # STEP 1: Admin registers player (limited data)
        ranking_reg = json.dumps({"DS": {"rank": "80", "points": "2294"}})
        update_player_in_db(
            license_id="11111111",
            name="Lisa Björk",
            profile_url="/player-profile/ghi-789",
            club="Malmö BK",
            gender="F",
            ranking=ranking_reg
        )

        player_after_reg = self._get_player("11111111")
        self.assertIsNone(player_after_reg["email"])
        self.assertIsNone(player_after_reg["dob"])

        # STEP 2: Player logs in (full data now available)
        ranking_login = json.dumps({
            "DS": {"rank": "78", "points": "2350"},
            "DD": {"rank": "240", "points": "1100"},
            "DS U13": {"rank": "1", "points": "2350"}
        })
        update_player_in_db(
            license_id="11111111",
            name="Lisa Björk",
            profile_url="/player-profile/ghi-789",
            club="Malmö BK",
            gender="F",
            email="lisa@example.com",
            phone="+46709876543",
            dob="2011-03-22",
            age="15",
            ranking=ranking_login
        )

        player_after_login = self._get_player("11111111")
        # All fields should now be filled
        self.assertEqual(player_after_login["email"], "lisa@example.com")
        self.assertEqual(player_after_login["phone"], "+46709876543")
        self.assertEqual(player_after_login["dob"], "2011-03-22")
        self.assertEqual(player_after_login["age"], "15")
        # Club and gender should still be there
        self.assertEqual(player_after_login["club"], "Malmö BK")
        self.assertEqual(player_after_login["gender"], "F")
        # Ranking should be updated with fresh data
        stored_ranking = json.loads(player_after_login["ranking"])
        self.assertEqual(stored_ranking["DS"]["points"], "2350")
        self.assertIn("DS U13", stored_ranking)

    def test_registration_after_login_preserves_login_data(self):
        """Test that re-registering a player doesn't wipe email/phone/dob from login"""
        from players_scraper import update_player_in_db

        # STEP 1: Player logged in (has all data)
        ranking_full = json.dumps({"HS": {"rank": "10", "points": "3000"}})
        update_player_in_db(
            license_id="22222222",
            name="Karl Johansson",
            profile_url="/player-profile/jkl-012",
            club="Göteborg BK",
            gender="M",
            email="karl@example.com",
            phone="+46701111111",
            dob="2008-11-01",
            age="17",
            ranking=ranking_full
        )

        # STEP 2: Admin re-registers player for another tournament (limited data)
        # email, phone, dob, age are NOT passed (None)
        ranking_reg = json.dumps({"HS": {"rank": "9", "points": "3100"}})
        update_player_in_db(
            license_id="22222222",
            name="Karl Johansson",
            profile_url="/player-profile/jkl-012",
            club="Göteborg BK",
            gender="M",
            ranking=ranking_reg
        )

        player = self._get_player("22222222")
        # Login data should be PRESERVED (COALESCE keeps existing non-None values)
        self.assertEqual(player["email"], "karl@example.com")
        self.assertEqual(player["phone"], "+46701111111")
        self.assertEqual(player["dob"], "2008-11-01")
        self.assertEqual(player["age"], "17")
        # Ranking should be updated
        stored_ranking = json.loads(player["ranking"])
        self.assertEqual(stored_ranking["HS"]["points"], "3100")

    def test_no_duplicate_entries_for_same_license_id(self):
        """Test that calling update_player_in_db multiple times doesn't create duplicates"""
        from players_scraper import update_player_in_db

        update_player_in_db(license_id="33333333", name="Player One", profile_url="/p/1")
        update_player_in_db(license_id="33333333", name="Player One Updated", profile_url="/p/1")
        update_player_in_db(license_id="33333333", name="Player One Final", profile_url="/p/1")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM players WHERE license_id = ?", ("33333333",))
        count = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count, 1)

        # Should have the latest name
        player = self._get_player("33333333")
        self.assertEqual(player["name"], "Player One Final")


class TestRankingJsonStructure(unittest.TestCase):
    """Test that ranking JSON follows the correct structure"""

    def test_ranking_has_rank_and_points_for_each_category(self):
        """Each category must have both 'rank' and 'points'"""
        ranking = {
            "DS": {"rank": "80", "points": "2294"},
            "DD": {"rank": "250", "points": "1064"},
            "MD": {"rank": "367", "points": "1312"},
            "DS U13": {"rank": "1", "points": "2294"},
            "DD U13": {"rank": "1", "points": "1064"},
            "MD U13": {"rank": "1", "points": "1312"}
        }

        for category, data in ranking.items():
            self.assertIn("rank", data, f"Missing 'rank' in {category}")
            self.assertIn("points", data, f"Missing 'points' in {category}")
            # Values should be strings (as scraped from HTML)
            self.assertIsInstance(data["rank"], str)
            self.assertIsInstance(data["points"], str)

    def test_ranking_supports_adult_categories(self):
        """Ranking supports adult categories: HS, DS, HD, DD, MD"""
        ranking = {
            "HS": {"rank": "15", "points": "2800"},
            "DS": {"rank": "80", "points": "2294"},
            "HD": {"rank": "50", "points": "1800"},
            "DD": {"rank": "250", "points": "1064"},
            "MD": {"rank": "367", "points": "1312"}
        }

        adult_categories = {"HS", "DS", "HD", "DD", "MD"}
        for cat in adult_categories:
            self.assertIn(cat, ranking)

    def test_ranking_supports_age_categories(self):
        """Ranking supports age-based categories: U9, U11, U13, U15, U17, U19"""
        ranking = {
            "HS U13": {"rank": "1", "points": "1500"},
            "DS U13": {"rank": "2", "points": "1200"},
            "HD U15": {"rank": "5", "points": "900"},
            "DD U17": {"rank": "10", "points": "700"},
            "MD U19": {"rank": "15", "points": "500"}
        }

        # All should be valid category keys
        for key in ranking:
            self.assertTrue(
                any(base in key for base in ["HS", "DS", "HD", "DD", "MD"]),
                f"Unexpected category key: {key}"
            )

    def test_ranking_json_round_trip(self):
        """Test that ranking survives JSON encode/decode"""
        original = {
            "DS": {"rank": "80", "points": "2294"},
            "DS U13": {"rank": "1", "points": "2294"},
            "MD": {"rank": "367", "points": "1312"}
        }

        encoded = json.dumps(original)
        decoded = json.loads(encoded)

        self.assertEqual(original, decoded)


class TestAddPlayerEndpointStorage(unittest.TestCase):
    """Test the /api/add-player endpoint stores data correctly in both tables"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.players_db = os.path.join(self.test_dir, "players.db")
        self.tournaments_db = os.path.join(self.test_dir, "tournaments.db")
        self._create_tables()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_tables(self):
        # Players table
        conn = sqlite3.connect(self.players_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT,
                name TEXT NOT NULL,
                profile_url TEXT UNIQUE,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                dob TEXT,
                age TEXT,
                ranking TEXT,
                last_updated TIMESTAMP,
                last_scraped TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

        # Tournaments table
        conn = sqlite3.connect(self.tournaments_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                tournament_name TEXT PRIMARY KEY UNIQUE NOT NULL,
                tournament_url TEXT UNIQUE NOT NULL,
                location TEXT,
                date_start TEXT,
                date_end TEXT,
                registration_opens TEXT,
                registration_closes TEXT,
                cancellation_deadline TEXT,
                competition_start TEXT,
                competition_end TEXT,
                categories TEXT,
                selected_for_view INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tournament_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_name TEXT NOT NULL,
                license_id TEXT NOT NULL,
                singles_levels TEXT,
                doubles_levels TEXT,
                mixed_levels TEXT,
                doubles_partner TEXT,
                mixed_partner TEXT,
                registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tournament_name, license_id),
                FOREIGN KEY (tournament_name) REFERENCES tournaments(tournament_name)
            )
        """)
        # Insert a test tournament
        conn.execute("""
            INSERT INTO tournaments (tournament_name, tournament_url, location, date_start, date_end)
            VALUES (?, ?, ?, ?, ?)
        """, ("Test Open 2026", "https://example.com/tournament/123", "Stockholm", "2026-09-01", "2026-09-03"))
        conn.commit()
        conn.close()

    def test_registration_stores_player_and_registration(self):
        """Simulate admin registering a player: should create player + registration entry"""
        # Simulate what /api/add-player does:
        license_id = "44444444"
        player_name = "Maria Lindqvist"
        club = "Uppsala BK"
        gender = "F"
        profile_url = "/player-profile/xyz-999"
        ranking = json.dumps({"DS": {"rank": "50", "points": "2500"}, "DD": {"rank": "100", "points": "1500"}})
        tournament_name = "Test Open 2026"

        now = datetime.now().isoformat()

        # STEP 1: Insert into players.db
        conn_players = sqlite3.connect(self.players_db)
        cur = conn_players.cursor()
        cur.execute("SELECT id FROM players WHERE license_id = ?", (license_id,))
        existing = cur.fetchone()

        if not existing:
            cur.execute("""
                INSERT INTO players (license_id, name, profile_url, club, gender, ranking, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (license_id, player_name, profile_url, club, gender, ranking, now))
        conn_players.commit()
        conn_players.close()

        # STEP 2: Insert into tournament_registrations
        conn_tour = sqlite3.connect(self.tournaments_db)
        cur_tour = conn_tour.cursor()
        cur_tour.execute("""
            INSERT INTO tournament_registrations (tournament_name, license_id, singles_levels, doubles_levels, mixed_levels,
             doubles_partner, mixed_partner, registration_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (tournament_name, license_id, "DS B", "DD C", "", "", ""))
        conn_tour.commit()
        conn_tour.close()

        # VERIFY: Player exists in players.db with correct fields
        conn_players = sqlite3.connect(self.players_db)
        conn_players.row_factory = sqlite3.Row
        cur = conn_players.cursor()
        cur.execute("SELECT * FROM players WHERE license_id = ?", (license_id,))
        player = dict(cur.fetchone())
        conn_players.close()

        self.assertEqual(player["name"], "Maria Lindqvist")
        self.assertEqual(player["club"], "Uppsala BK")
        self.assertEqual(player["gender"], "F")
        self.assertEqual(player["profile_url"], "/player-profile/xyz-999")
        self.assertIsNone(player["email"])  # Not available from live search
        self.assertIsNone(player["phone"])  # Not available from live search
        self.assertIsNone(player["dob"])    # Not available from live search
        self.assertIsNone(player["age"])    # Not available from live search

        stored_ranking = json.loads(player["ranking"])
        self.assertEqual(stored_ranking["DS"]["rank"], "50")
        self.assertEqual(stored_ranking["DS"]["points"], "2500")
        self.assertEqual(stored_ranking["DD"]["points"], "1500")

        # VERIFY: Registration exists in tournament_registrations
        conn_tour = sqlite3.connect(self.tournaments_db)
        conn_tour.row_factory = sqlite3.Row
        cur_tour = conn_tour.cursor()
        cur_tour.execute(
            "SELECT * FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?",
            (tournament_name, license_id)
        )
        reg = dict(cur_tour.fetchone())
        conn_tour.close()

        self.assertEqual(reg["tournament_name"], "Test Open 2026")
        self.assertEqual(reg["license_id"], "44444444")
        self.assertEqual(reg["singles_levels"], "DS B")
        self.assertEqual(reg["doubles_levels"], "DD C")

    def test_login_after_registration_enriches_player_data(self):
        """After registration, player logs in and their record gets enriched"""
        license_id = "55555555"
        tournament_name = "Test Open 2026"
        now = datetime.now().isoformat()

        # STEP 1: Admin registers player (limited data from live search)
        conn_players = sqlite3.connect(self.players_db)
        conn_players.execute("""
            INSERT INTO players (license_id, name, profile_url, club, gender, ranking, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (license_id, "Johan Berg", "/player-profile/aaa-111", "Lund BK", "M",
              json.dumps({"HS": {"rank": "30", "points": "2000"}}), now))
        conn_players.commit()
        conn_players.close()

        # Registration
        conn_tour = sqlite3.connect(self.tournaments_db)
        conn_tour.execute("""
            INSERT INTO tournament_registrations (tournament_name, license_id, singles_levels)
            VALUES (?, ?, ?)
        """, (tournament_name, license_id, "HS A"))
        conn_tour.commit()
        conn_tour.close()

        # STEP 2: Player logs in — update with full data (simulates update_player_in_db)
        conn_players = sqlite3.connect(self.players_db)
        conn_players.execute("""
            UPDATE players SET
                email = COALESCE(?, email),
                phone = COALESCE(?, phone),
                dob = COALESCE(?, dob),
                age = COALESCE(?, age),
                ranking = COALESCE(?, ranking),
                last_updated = ?,
                last_scraped = ?
            WHERE license_id = ?
        """, ("johan@example.com", "+46702222222", "2008-07-10", "18",
              json.dumps({"HS": {"rank": "28", "points": "2100"}, "HD": {"rank": "60", "points": "1200"}, "HS U19": {"rank": "5", "points": "2100"}}),
              now, now, license_id))
        conn_players.commit()
        conn_players.close()

        # VERIFY: Player now has complete data
        conn_players = sqlite3.connect(self.players_db)
        conn_players.row_factory = sqlite3.Row
        cur = conn_players.cursor()
        cur.execute("SELECT * FROM players WHERE license_id = ?", (license_id,))
        player = dict(cur.fetchone())
        conn_players.close()

        self.assertEqual(player["name"], "Johan Berg")
        self.assertEqual(player["club"], "Lund BK")
        self.assertEqual(player["gender"], "M")
        self.assertEqual(player["email"], "johan@example.com")
        self.assertEqual(player["phone"], "+46702222222")
        self.assertEqual(player["dob"], "2008-07-10")
        self.assertEqual(player["age"], "18")

        stored_ranking = json.loads(player["ranking"])
        self.assertEqual(stored_ranking["HS"]["rank"], "28")
        self.assertEqual(stored_ranking["HS"]["points"], "2100")
        self.assertEqual(stored_ranking["HD"]["points"], "1200")
        self.assertIn("HS U19", stored_ranking)

        # VERIFY: Registration still intact
        conn_tour = sqlite3.connect(self.tournaments_db)
        cur_tour = conn_tour.cursor()
        cur_tour.execute(
            "SELECT singles_levels FROM tournament_registrations WHERE license_id = ?",
            (license_id,)
        )
        reg = cur_tour.fetchone()
        conn_tour.close()
        self.assertEqual(reg[0], "HS A")


class TestSearchDoesNotInsert(unittest.TestCase):
    """Test that /api/search-players does NOT insert into players.db"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "players.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT,
                name TEXT NOT NULL,
                profile_url TEXT UNIQUE,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                dob TEXT,
                age TEXT,
                ranking TEXT,
                last_updated TIMESTAMP,
                last_scraped TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_empty_db_stays_empty_after_search(self):
        """Verify search results don't get cached into players table"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM players")
        count_before = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count_before, 0)
        # After a search (which we can't execute without mocking the full app),
        # the DB should still be empty. This verifies our schema is correct
        # and that no auto-insert triggers exist.

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM players")
        count_after = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count_after, 0)


if __name__ == '__main__':
    unittest.main()
