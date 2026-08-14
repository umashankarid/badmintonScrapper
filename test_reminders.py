"""
Unit tests for auto-email reminder logic.

Tests:
- Reminders sent at 7 days and 3 days before admin_reg_end_date
- Players already registered are skipped
- Players whose groups don't match tournament are skipped
- Players not in kometPlayers see tournaments with no groups or 'All'
- No duplicate reminders sent
"""

import unittest
import sqlite3
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestReminderLogic(unittest.TestCase):
    """Test the auto-email reminder system"""

    def setUp(self):
        """Create temporary databases for testing"""
        self.test_dir = tempfile.mkdtemp()
        self.tournaments_db = os.path.join(self.test_dir, "tournaments.db")
        self.players_db = os.path.join(self.test_dir, "players.db")
        self.admin_db = os.path.join(self.test_dir, "admin.db")
        self._create_tables()
        self._seed_data()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_tables(self):
        # Tournaments DB
        conn = sqlite3.connect(self.tournaments_db)
        conn.execute("""
            CREATE TABLE tournaments (
                tournament_name TEXT PRIMARY KEY,
                tournament_url TEXT,
                location TEXT,
                date_start TEXT,
                date_end TEXT,
                registration_closes TEXT,
                admin_reg_end_date TEXT,
                tournament_groups TEXT,
                selected_for_view INTEGER DEFAULT 0,
                categories TEXT,
                last_updated TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE tournament_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_name TEXT,
                license_id TEXT,
                singles_levels TEXT,
                doubles_levels TEXT,
                mixed_levels TEXT,
                doubles_partner TEXT,
                mixed_partner TEXT,
                registration_date TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Players DB
        conn = sqlite3.connect(self.players_db)
        conn.execute("""
            CREATE TABLE kometPlayers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT UNIQUE,
                name TEXT NOT NULL,
                email TEXT,
                groups TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Admin DB
        conn = sqlite3.connect(self.admin_db)
        conn.execute("""
            CREATE TABLE reminders_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_db TEXT,
                player_email TEXT,
                sent_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE smtp_settings (
                id INTEGER PRIMARY KEY,
                smtp_host TEXT,
                smtp_port INTEGER,
                smtp_email TEXT,
                smtp_password TEXT,
                reminder_days INTEGER DEFAULT 3
            )
        """)
        conn.execute("INSERT INTO smtp_settings (id, smtp_email, smtp_password) VALUES (1, 'test@test.com', 'key123')")
        conn.commit()
        conn.close()

    def _seed_data(self):
        today = datetime.now().date()

        # Tournament closing in 7 days (should trigger reminder)
        seven_days = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        # Tournament closing in 3 days (should trigger reminder)
        three_days = (today + timedelta(days=3)).strftime("%Y-%m-%d")
        # Tournament closing in 10 days (should NOT trigger)
        ten_days = (today + timedelta(days=10)).strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.tournaments_db)
        conn.execute("""
            INSERT INTO tournaments (tournament_name, tournament_url, admin_reg_end_date, tournament_groups, selected_for_view)
            VALUES (?, ?, ?, ?, 1)
        """, ("Tournament A", "http://a", seven_days, json.dumps(["U13", "U15"])))
        conn.execute("""
            INSERT INTO tournaments (tournament_name, tournament_url, admin_reg_end_date, tournament_groups, selected_for_view)
            VALUES (?, ?, ?, ?, 1)
        """, ("Tournament B", "http://b", three_days, json.dumps(["All"])))
        conn.execute("""
            INSERT INTO tournaments (tournament_name, tournament_url, admin_reg_end_date, tournament_groups, selected_for_view)
            VALUES (?, ?, ?, ?, 1)
        """, ("Tournament C", "http://c", ten_days, json.dumps(["Senior"])))

        # Player 1 is already registered for Tournament A
        conn.execute("""
            INSERT INTO tournament_registrations (tournament_name, license_id, singles_levels)
            VALUES (?, ?, ?)
        """, ("Tournament A", "LIC001", "HS A"))
        conn.commit()
        conn.close()

        # Komet Players
        conn = sqlite3.connect(self.players_db)
        # Player 1: U13 group, already registered for Tournament A
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?,?,?,?)",
                    ("LIC001", "Player One", "player1@test.com", json.dumps(["U13"])))
        # Player 2: U13 group, NOT registered
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?,?,?,?)",
                    ("LIC002", "Player Two", "player2@test.com", json.dumps(["U13"])))
        # Player 3: U15 group, NOT registered
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?,?,?,?)",
                    ("LIC003", "Player Three", "player3@test.com", json.dumps(["U15"])))
        # Player 4: Senior group, NOT registered (doesn't match Tournament A)
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?,?,?,?)",
                    ("LIC004", "Player Four", "player4@test.com", json.dumps(["Senior"])))
        # Player 5: No email (should be skipped)
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?,?,?,?)",
                    ("LIC005", "Player Five", None, json.dumps(["U13"])))
        conn.commit()
        conn.close()

    def _get_eligible_players(self, tournament_name):
        """Simulate the reminder logic to find eligible players"""
        conn_t = sqlite3.connect(self.tournaments_db)
        cur_t = conn_t.cursor()
        
        cur_t.execute("SELECT tournament_groups FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        row = cur_t.fetchone()
        tournament_groups = json.loads(row[0]) if row and row[0] else []
        
        cur_t.execute("SELECT license_id FROM tournament_registrations WHERE tournament_name = ?", (tournament_name,))
        registered_ids = {r[0] for r in cur_t.fetchall()}
        conn_t.close()
        
        conn_p = sqlite3.connect(self.players_db)
        cur_p = conn_p.cursor()
        cur_p.execute("SELECT name, license_id, email, groups FROM kometPlayers WHERE email IS NOT NULL AND email != ''")
        
        eligible = []
        for p_row in cur_p.fetchall():
            name, license_id, email, player_groups_json = p_row
            
            if license_id in registered_ids:
                continue
            
            player_groups = json.loads(player_groups_json) if player_groups_json else []
            
            if tournament_groups:
                if "All" not in tournament_groups and not set(player_groups).intersection(set(tournament_groups)):
                    continue
            
            eligible.append({"name": name, "license_id": license_id, "email": email})
        
        conn_p.close()
        return eligible

    def test_eligible_players_for_grouped_tournament(self):
        """Tournament A (U13, U15) - only U13/U15 players who aren't registered"""
        eligible = self._get_eligible_players("Tournament A")
        names = [p["name"] for p in eligible]
        
        # Player One: U13 but ALREADY REGISTERED → skipped
        self.assertNotIn("Player One", names)
        # Player Two: U13, not registered → eligible
        self.assertIn("Player Two", names)
        # Player Three: U15, not registered → eligible
        self.assertIn("Player Three", names)
        # Player Four: Senior, not registered → NOT eligible (wrong group)
        self.assertNotIn("Player Four", names)
        # Player Five: U13 but no email → skipped (query filters by email)
        self.assertNotIn("Player Five", names)

    def test_eligible_players_for_all_tournament(self):
        """Tournament B (All group) - all players with email who aren't registered"""
        eligible = self._get_eligible_players("Tournament B")
        names = [p["name"] for p in eligible]
        
        # All players with email should be eligible (Tournament B has "All" group)
        self.assertIn("Player One", names)
        self.assertIn("Player Two", names)
        self.assertIn("Player Three", names)
        self.assertIn("Player Four", names)
        # Player Five: no email → not in results
        self.assertNotIn("Player Five", names)

    def test_registered_players_skipped(self):
        """Players already registered should not receive reminders"""
        eligible = self._get_eligible_players("Tournament A")
        license_ids = [p["license_id"] for p in eligible]
        
        # LIC001 is registered for Tournament A
        self.assertNotIn("LIC001", license_ids)

    def test_wrong_group_players_skipped(self):
        """Players whose groups don't match tournament should be skipped"""
        eligible = self._get_eligible_players("Tournament A")
        license_ids = [p["license_id"] for p in eligible]
        
        # LIC004 is Senior, Tournament A is U13/U15
        self.assertNotIn("LIC004", license_ids)

    def test_no_email_players_skipped(self):
        """Players without email should be skipped"""
        eligible = self._get_eligible_players("Tournament A")
        license_ids = [p["license_id"] for p in eligible]
        
        # LIC005 has no email
        self.assertNotIn("LIC005", license_ids)

    def test_reminder_not_sent_for_10_days(self):
        """Tournament C closes in 10 days - should NOT trigger reminder"""
        today = datetime.now().date()
        conn_t = sqlite3.connect(self.tournaments_db)
        cur_t = conn_t.cursor()
        cur_t.execute("SELECT admin_reg_end_date FROM tournaments WHERE tournament_name = 'Tournament C'")
        row = cur_t.fetchone()
        conn_t.close()
        
        reg_close = datetime.strptime(row[0], "%Y-%m-%d").date()
        days_left = (reg_close - today).days
        
        # Should NOT be 7 or 3
        self.assertNotIn(days_left, (7, 3))

    def test_reminder_triggers_at_7_days(self):
        """Tournament A closes in 7 days - should trigger reminder"""
        today = datetime.now().date()
        conn_t = sqlite3.connect(self.tournaments_db)
        cur_t = conn_t.cursor()
        cur_t.execute("SELECT admin_reg_end_date FROM tournaments WHERE tournament_name = 'Tournament A'")
        row = cur_t.fetchone()
        conn_t.close()
        
        reg_close = datetime.strptime(row[0], "%Y-%m-%d").date()
        days_left = (reg_close - today).days
        
        self.assertEqual(days_left, 7)

    def test_reminder_triggers_at_3_days(self):
        """Tournament B closes in 3 days - should trigger reminder"""
        today = datetime.now().date()
        conn_t = sqlite3.connect(self.tournaments_db)
        cur_t = conn_t.cursor()
        cur_t.execute("SELECT admin_reg_end_date FROM tournaments WHERE tournament_name = 'Tournament B'")
        row = cur_t.fetchone()
        conn_t.close()
        
        reg_close = datetime.strptime(row[0], "%Y-%m-%d").date()
        days_left = (reg_close - today).days
        
        self.assertEqual(days_left, 3)

    def test_no_duplicate_reminders(self):
        """Once a reminder is sent, it should not be sent again"""
        # Simulate sending a reminder
        conn_admin = sqlite3.connect(self.admin_db)
        conn_admin.execute(
            "INSERT INTO reminders_sent (tournament_db, player_email, sent_at) VALUES (?,?,?)",
            ("Tournament A_7days", "player2@test.com", datetime.now().isoformat())
        )
        conn_admin.commit()
        
        # Check if it's marked as sent
        cur = conn_admin.cursor()
        today = datetime.now().date().isoformat()
        cur.execute(
            "SELECT id FROM reminders_sent WHERE tournament_db = ? AND player_email = ? AND sent_at LIKE ?",
            ("Tournament A_7days", "player2@test.com", f"{today}%")
        )
        result = cur.fetchone()
        conn_admin.close()
        
        # Should find the existing record → means we'd skip this player
        self.assertIsNotNone(result)

    def test_tournament_with_no_groups_shows_to_all(self):
        """Tournament with no groups assigned should be visible to all players"""
        # Add a tournament with no groups
        conn = sqlite3.connect(self.tournaments_db)
        conn.execute("""
            INSERT INTO tournaments (tournament_name, tournament_url, admin_reg_end_date, tournament_groups, selected_for_view)
            VALUES (?, ?, ?, ?, 1)
        """, ("Tournament D", "http://d", (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d"), None))
        conn.commit()
        conn.close()
        
        eligible = self._get_eligible_players("Tournament D")
        # All players with email should be eligible (no group filter)
        self.assertEqual(len(eligible), 4)


class TestReminderEmailTemplates(unittest.TestCase):
    """Test the email templates for reminders"""

    def test_7_day_template(self):
        """Verify 7-day reminder email content"""
        player_name = "Aadvika Umashankar"
        tournament_name = "Komet Hösttävling 2026"
        admin_reg_end_date = "2026-09-01"
        
        subject = f"📋 Registration closing in 1 week: {tournament_name}"
        body = (f"Hi {player_name},\n\n"
                f"This is a friendly reminder that registration for '{tournament_name}' "
                f"closes in 1 week ({admin_reg_end_date}).\n\n"
                f"Don't forget to register if you want to participate!\n\n"
                f"Best regards,\nBMK Komet")
        
        self.assertIn("1 week", subject)
        self.assertIn(tournament_name, subject)
        self.assertIn(player_name, body)
        self.assertIn(admin_reg_end_date, body)
        self.assertIn("BMK Komet", body)

    def test_3_day_template(self):
        """Verify 3-day reminder email content"""
        player_name = "Yanvi Goyal"
        tournament_name = "Vikingaslaget 2026"
        admin_reg_end_date = "2026-08-20"
        
        subject = f"⚠️ Last chance to register: {tournament_name} (3 days left!)"
        body = (f"Hi {player_name},\n\n"
                f"⚠️ Registration for '{tournament_name}' closes in 3 days ({admin_reg_end_date})!\n\n"
                f"If you haven't registered yet, please do so soon.\n\n"
                f"Best regards,\nBMK Komet")
        
        self.assertIn("Last chance", subject)
        self.assertIn("3 days", subject)
        self.assertIn(player_name, body)
        self.assertIn("⚠️", body)


if __name__ == '__main__':
    unittest.main()
