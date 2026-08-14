import os
import json
import sqlite3
import requests as ext_requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, session, send_from_directory, redirect
from drive_sync import download_all, upload_all
import atexit
import logging
import threading
import time
import os
import sys
import unittest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "supersecretkey"

# ==================== PRE-STARTUP TEST VERIFICATION ====================
def run_startup_tests():
    """Run unit tests before startup - block if any fail"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("🧪 Running Pre-Startup Unit Tests")
    logger.info("=" * 70)
    
    try:
        # Discover and run tests
        loader = unittest.TestLoader()
        suite = loader.discover('.', pattern='test_badminton.py')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        logger.info("")
        logger.info("=" * 70)
        
        if result.wasSuccessful():
            logger.info(f"✅ ALL {result.testsRun} TESTS PASSED - Startup approved")
            logger.info("=" * 70)
            return True
        else:
            logger.error(f"❌ TEST FAILURES DETECTED: {len(result.failures)} failures, {len(result.errors)} errors")
            logger.error("=" * 70)
            
            # Show failures
            if result.failures:
                logger.error("\n❌ FAILURES:")
                for test, trace in result.failures:
                    logger.error(f"  {test}: {trace[:200]}")
            
            # Show errors
            if result.errors:
                logger.error("\n❌ ERRORS:")
                for test, trace in result.errors:
                    logger.error(f"  {test}: {trace[:200]}")
            
            logger.error("")
            logger.error("=" * 70)
            logger.error("❌ BUILD BLOCKED: Fix failing tests before startup")
            logger.error("=" * 70)
            return False
    
    except Exception as e:
        logger.error(f"❌ Error running startup tests: {str(e)}")
        logger.error("⚠️  Continuing anyway (tests may not be available)")
        return True  # Don't block if tests can't be run

# Run tests before startup
if not run_startup_tests():
    logger.error("❌ STARTUP ABORTED: Unit tests failed")
    sys.exit(1)

# Sync databases on startup
logger.info("🔄 Starting Dropbox database sync...")
try:
    download_all()
except Exception as e:
    logger.error(f"⚠️  Failed to download from Dropbox on startup: {str(e)}")
    logger.error("⚠️  Continuing with local databases (new data will NOT persist)")




# ==================== DEBOUNCE SYNC SYSTEM ====================
# Debounce settings
DEBOUNCE_DELAY = 10  # Wait 10 seconds after last change before syncing
PERIODIC_SYNC_INTERVAL = 300  # Fallback periodic sync every 5 minutes

# Debounce state
_sync_timer = None
_sync_lock = threading.Lock()
_last_sync_time = time.time()

def _debounced_sync():
    """Internal function to perform the sync"""
    global _sync_timer
    try:
        logger.info("📤 Debounced sync: Uploading databases to Dropbox...")
        upload_all()
        logger.info("✅ Debounced sync completed")
    except Exception as e:
        logger.error(f"❌ Error in debounced sync: {str(e)}")
    finally:
        _sync_timer = None

def trigger_sync():
    """
    Trigger a debounced sync.
    Call this after any database change.
    Will upload within DEBOUNCE_DELAY seconds.
    """
    global _sync_timer
    
    with _sync_lock:
        # Cancel existing timer if any
        if _sync_timer is not None:
            _sync_timer.cancel()
        
        # Schedule new sync after delay
        _sync_timer = threading.Timer(DEBOUNCE_DELAY, _debounced_sync)
        _sync_timer.daemon = True
        _sync_timer.start()

def periodic_sync_fallback():
    """Fallback periodic sync (every 5 minutes) to ensure backup"""
    while True:
        try:
            time.sleep(PERIODIC_SYNC_INTERVAL)
            logger.info("⏱️  Periodic fallback sync: Uploading databases to Dropbox...")
            upload_all()
        except Exception as e:
            logger.error(f"❌ Error in periodic sync: {str(e)}")

# Register upload on shutdown
def sync_on_shutdown():
    """Upload databases to Dropbox on shutdown"""
    logger.info("💾 Syncing databases to Dropbox on shutdown...")
    # Cancel pending debounce timer
    global _sync_timer
    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
    # Final upload
    upload_all()

atexit.register(sync_on_shutdown)

# Start background fallback sync thread
fallback_sync_thread = threading.Thread(target=periodic_sync_fallback, daemon=True)
fallback_sync_thread.start()
logger.info("✅ Fallback sync thread started (every 5 minutes)")
logger.info("✅ Debounce sync ready (10 seconds after changes)")

PLAYERS_DB = os.path.join(os.path.dirname(__file__), "players.db")


POINTS_DB = os.path.join(os.path.dirname(__file__), "point_rules.db")
ADMIN_DB = os.path.join(os.path.dirname(__file__), "admin.db")
TOURNAMENTS_DB = os.path.join(os.path.dirname(__file__), "tournaments.db")

def init_tournaments_db():
    """Initialize tournaments.db with tournament and registration tables"""
    conn = sqlite3.connect(TOURNAMENTS_DB)
    
    # Tournament metadata table - tournament_name is PRIMARY KEY
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            tournament_name TEXT PRIMARY KEY UNIQUE NOT NULL,
            tournament_url TEXT UNIQUE NOT NULL,
            location TEXT,
            date_start TEXT,
            date_end TEXT,
            registration_opens TEXT,
            registration_closes TEXT,
            admin_reg_end_date TEXT,
            cancellation_deadline TEXT,
            competition_start TEXT,
            competition_end TEXT,
            categories TEXT,
            selected_for_view INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add admin_reg_end_date column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE tournaments ADD COLUMN admin_reg_end_date TEXT")
    except Exception:
        pass  # Column already exists
    
    # Add tournament_groups column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE tournaments ADD COLUMN tournament_groups TEXT")
    except Exception:
        pass  # Column already exists
    
    # Reminder opt-out table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminder_opt_out (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            tournament_name TEXT NOT NULL,
            UNIQUE(license_id, tournament_name)
        )
    """)
    
    # Player registrations for tournaments - references tournament_name
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
            FOREIGN KEY (tournament_name) REFERENCES tournaments(tournament_name),
            FOREIGN KEY (license_id) REFERENCES players(license_id)
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ tournaments.db initialized with tournaments and tournament_registrations tables")


def init_admin_db():
    conn = sqlite3.connect(ADMIN_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT,
            email TEXT
        )
    """)
    # Add email column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE admin_users ADD COLUMN email TEXT")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smtp_settings (
            id INTEGER PRIMARY KEY,
            smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,
            smtp_email TEXT,
            smtp_password TEXT,
            reminder_days INTEGER DEFAULT 3
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_db TEXT,
            player_email TEXT,
            sent_at TEXT
        )
    """)
    conn.commit()
    
    # Insert default admin if it doesn't exist
    try:
        conn.execute("INSERT INTO admin_users (username) VALUES (?)", ("umashankar1985@gmail.com",))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    try:
        conn.execute("INSERT INTO admin_users (username) VALUES (?)", ("sbf04959",))
        conn.commit()
        logger.info("Created default admin: sbf04959 (club account)")
    except sqlite3.IntegrityError:
        pass
    
    conn.close()


init_admin_db()
init_tournaments_db()


def is_admin_user(username):
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM admin_users WHERE username=?", (username,))
    result = cur.fetchone()
    conn.close()
    return result is not None


def init_point_rules_db():
    conn = sqlite3.connect(POINTS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS point_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            klass TEXT NOT NULL,
            hs_min INTEGER,
            hs_max INTEGER,
            ds_min INTEGER,
            ds_max INTEGER,
            hd_min INTEGER,
            hd_max INTEGER,
            dd_min INTEGER,
            dd_max INTEGER,
            md_min INTEGER,
            md_max INTEGER
        )
    """)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM point_rules")
    if cur.fetchone()[0] == 0:
        rules = [
            ("Elit", 3500, None, 2250, None, 3500, None, 2250, None, 3000, None),
            ("A", 1300, 7000, 1100, 6000, 1300, 7000, 1100, 6000, 1100, 5000),
            ("B", 300, 1700, 200, 1500, 300, 1700, 200, 1500, 200, 1500),
            ("C", 0, 500, 0, 400, 0, 500, 0, 400, 0, 400),
            ("D", 0, 100, 0, 100, 0, 100, 0, 100, 0, 100),
        ]
        conn.executemany(
            "INSERT INTO point_rules (klass, hs_min, hs_max, ds_min, ds_max, hd_min, hd_max, dd_min, dd_max, md_min, md_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rules
        )
    conn.commit()
    conn.close()


init_point_rules_db()

# Upload initialized databases to Dropbox immediately on startup
logger.info("📤 Uploading initialized databases to Dropbox...")
upload_all()
logger.info("✅ Databases backed up on startup")



def get_tournament_db(db_file):
    """
    DEPRECATED: Legacy function for per-tournament DB access
    This is being phased out - all tournament data should use tournaments.db
    """
    logger.warning(f"⚠️  DEPRECATED: get_tournament_db() called with {db_file} - this is legacy code")
    return None  # Return None to indicate this path is not supported


# ==================== TOURNAMENTS.DB HELPER FUNCTIONS ====================

def get_tournament_by_url(tournament_url):
    """Get tournament metadata by URL"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end, selected_for_view
            FROM tournaments WHERE tournament_url=?
        """, (tournament_url,))
        
        row = cur.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "tournament_name": row[1],
                "location": row[2],
                "date_start": row[3],
                "date_end": row[4],
                "registration_opens": row[5],
                "registration_closes": row[6],
                "cancellation_deadline": row[7],
                "competition_start": row[8],
                "competition_end": row[9],
                "selected_for_view": row[10]
            }
        return None
    except Exception as e:
        logger.error(f"❌ Error getting tournament by URL: {e}")
        return None


def get_player_registrations_for_tournament(tournament_name):
    """Get all player registrations for a tournament with player data via JOIN"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        # Need to attach players database to query it
        conn.execute(f"ATTACH DATABASE 'players.db' AS players_db")
        cur = conn.cursor()
        
        # NORMALIZED QUERY: JOIN with players table to get player data
        cur.execute("""
            SELECT p.name, r.license_id, p.club, p.gender, p.email, p.phone,
                   r.singles_levels, r.doubles_levels, r.mixed_levels,
                   r.doubles_partner, r.mixed_partner, r.registration_date
            FROM tournament_registrations r
            JOIN players_db.players p ON r.license_id = p.license_id
            WHERE r.tournament_name=?
            ORDER BY r.registration_date DESC
        """, (tournament_name,))
        
        rows = cur.fetchall()
        conn.close()
        
        registrations = []
        for row in rows:
            registrations.append({
                "player_name": row[0],
                "license_id": row[1],
                "club": row[2],
                "gender": row[3],
                "email": row[4],
                "phone": row[5],
                "singles_levels": row[6],
                "doubles_levels": row[7],
                "mixed_levels": row[8],
                "doubles_partner": row[9],
                "mixed_partner": row[10],
                "registration_date": row[11]
            })
        
        return registrations
    except Exception as e:
        logger.debug(f"No registrations found or table error: {e}")
        return []


def register_player_in_tournament(tournament_name, player_name, license_id, club, gender, email, phone, dob, age, ranking, singles_levels, doubles_levels, mixed_levels, doubles_partner, mixed_partner):
    """Register a player for a tournament (uses normalized schema with FK to players)"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        
        # NORMALIZED: Store only tournament-specific fields + license_id FK
        # Player data (name, club, gender, email, phone, dob, age, ranking) come from players table
        conn.execute("""
            INSERT INTO tournament_registrations (tournament_name, license_id, singles_levels, doubles_levels, mixed_levels, 
             doubles_partner, mixed_partner)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tournament_name, license_id, singles_levels, doubles_levels, mixed_levels, 
              doubles_partner, mixed_partner))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Registered {player_name} ({license_id}) for tournament {tournament_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Error registering player: {e}")
        return False


def delete_player_from_tournament(tournament_name, license_id):
    """Delete a player registration from a tournament"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        
        conn.execute("""
            DELETE FROM tournament_registrations
            WHERE tournament_name=? AND license_id=?
        """, (tournament_name, license_id))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Removed player {license_id} from tournament {tournament_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Error deleting player: {e}")
        return False


def get_player_club(player_name):
    """Look up a player's club from the scraped players DB."""
    conn = sqlite3.connect(PLAYERS_DB)
    cur = conn.cursor()
    cur.execute("SELECT club FROM players WHERE name=? LIMIT 1", (player_name,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


def get_player_license(player_name):
    """Look up a player's license ID from Badminton Sweden search."""
    try:
        resp = ext_requests.get(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": player_name},
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"},
            timeout=5
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("li.list__item"):
            name_el = item.select_one("a.media__link span.nav-link__value")
            if name_el and name_el.get_text(strip=True).lower() == player_name.lower():
                license_el = item.select_one(".media__title-aside")
                if license_el:
                    return license_el.get_text(strip=True).strip("()")
    except Exception:
        pass
    return ""


def get_player_ranking(player_name):
    """Fetch a player's ranking by searching for their profile and visiting the ranking page."""
    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        # Search for the player to get their profile URL
        resp = s.get(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": player_name},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=5
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        profile_url = ""
        for item in soup.select("li.list__item"):
            name_el = item.select_one("a.media__link span.nav-link__value")
            if name_el and name_el.get_text(strip=True).lower() == player_name.lower():
                link = item.select_one("a.media__link")
                if link:
                    profile_url = link.get("href", "")
                break

        if not profile_url:
            return ""

        # Fetch ranking page
        ranking_resp = s.get(
            f"https://badmintonsweden.tournamentsoftware.com{profile_url}/ranking",
            timeout=5
        )
        ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
        table = ranking_soup.find("table")
        if not table:
            return ""

        ranking = {}
        for row in table.find_all("tr")[1:]:
            th = row.find("th", scope="row")
            tds = row.find_all("td")
            if th and len(tds) >= 2:
                category = th.get_text(strip=True)
                if category:
                    rank = tds[0].get_text(strip=True)
                    points = tds[1].get_text(strip=True)
                    ranking[category] = {"rank": rank, "points": points}
        return json.dumps(ranking) if ranking else ""
    except Exception:
        return ""


def init_players_db():
    """Initialize players.db with new schema"""
    conn = sqlite3.connect(PLAYERS_DB)
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kometPlayers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT UNIQUE,
            name TEXT NOT NULL,
            email TEXT,
            groups TEXT
        )
    """)
    # Add groups column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE kometPlayers ADD COLUMN groups TEXT")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT UNIQUE NOT NULL
        )
    """)
    # Insert default "All" group if it doesn't exist
    try:
        conn.execute("INSERT OR IGNORE INTO player_groups (group_name) VALUES ('All')")
    except Exception:
        pass
    conn.commit()
    conn.close()


init_players_db()

# Initialize allplayers table (but don't start background scraper for now)
from players_scraper import init_allplayers_table
init_allplayers_table()
_allplayers_thread = None  # Scraper disabled


# --- Static pages ---
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/tournament.html")
def tournament_page():
    return send_from_directory("templates", "tournament.html")


@app.route("/admin.html")
def admin_page():
    return send_from_directory("templates", "admin.html")


@app.route("/manage-tournaments.html")
def manage_tournaments_page():
    return send_from_directory("templates", "manage-tournaments.html")


@app.route("/add-remove-tournaments.html")
def add_remove_tournaments_page():
    return send_from_directory("templates", "add-remove-tournaments.html")


@app.route("/manage-admins.html")
def manage_admins_page():
    return send_from_directory("templates", "manage-admins.html")


@app.route("/manage.html")
def manage_page():
    return send_from_directory("templates", "manage.html")


@app.route("/manage-komet-players.html")
def manage_komet_players_page():
    return send_from_directory("templates", "manage-komet-players.html")


@app.route("/email-settings.html")
def email_settings_page():
    return send_from_directory("templates", "email-settings.html")


@app.route("/send-email.html")
def send_email_page():
    return send_from_directory("templates", "send-email.html")


@app.route("/login.html")
def login_page():
    return send_from_directory("templates", "login.html")


@app.route("/manage-db.html")
def manage_db_page():
    """Admin-only page for viewing and managing databases"""
    if not session.get("admin"):
        logger.warning("⚠️  Unauthenticated user attempted to access /manage-db.html")
        return redirect("/login.html")
    
    logger.info("📊 Admin accessed Manage DB page")
    return send_from_directory("templates", "manage-db.html")


# --- Badminton Sweden Login ---
@app.route("/api/bwf-login", methods=["POST"])
def bwf_login():
    data = request.json
    login = data.get("login", "")
    password = data.get("password", "")
    if not login or not password:
        return jsonify(success=False, error="Login and password required"), 400

    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})

        # Accept cookies
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/user",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=10)

        # Get login page for verification token
        resp = s.get("https://badmintonsweden.tournamentsoftware.com/user", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        token_el = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_el:
            return jsonify(success=False, error="Could not load login page"), 500

        # Submit login
        logo_el = soup.find("input", {"name": "LogoUrl"})
        resp = s.post("https://badmintonsweden.tournamentsoftware.com/user", data={
            "__RequestVerificationToken": token_el.get("value", ""),
            "ReturnUrl": "/",
            "LogoUrl": logo_el.get("value", "") if logo_el else "",
            "Login": login,
            "Password": password
        }, allow_redirects=True, timeout=10)

        soup = BeautifulSoup(resp.text, "html.parser")

        # Check if login failed - still on login page
        login_input = soup.find("input", {"name": "Login"})
        if login_input:
            return jsonify(success=False, error="Invalid login credentials"), 401

        # After login, find the profile link in the nav ("Min profil" -> /player-profile/<UUID>)
        profile_url = ""
        profile_link = soup.select_one("a[href*='player-profile']")
        if not profile_link:
            # Try fetching homepage explicitly
            resp = s.get("https://badmintonsweden.tournamentsoftware.com/", timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            profile_link = soup.select_one("a[href*='player-profile']")

        if profile_link:
            profile_url = profile_link.get("href", "")

        print(f"[BWF Login] Profile URL found: {profile_url}")

        if not profile_url:
            # Club account (no player profile) - check if it's a known admin account
            if login in ("sbf04959", "umashankar1985@gmail.com"):
                # Club/admin account - proceed without player profile
                player_name = login
                name_el = soup.select_one(".masthead__user-title")
                if name_el:
                    player_name = name_el.get_text(strip=True)
                
                session["bwf_player"] = player_name
                session["bwf_login"] = login
                session["bwf_license_id"] = ""
                session["bwf_club"] = ""
                session["bwf_gender"] = ""
                session["bwf_email"] = ""
                session["bwf_phone"] = ""
                session["bwf_dob"] = ""
                session["bwf_age"] = ""
                session["bwf_ranking"] = {}
                session["admin"] = True
                logger.info(f"✅ Club/admin account logged in: {login}")
                return jsonify(success=True, player_name=player_name, license_id="", club="", gender="", email="", phone="", dob="", age="", ranking={})
            else:
                return jsonify(success=False, error="Login succeeded but could not find player profile"), 500

        # Get player name from the masthead (shown after login)
        player_name = ""
        license_id = ""
        club = ""

        name_el = soup.select_one(".masthead__user-title")
        if name_el:
            player_name = name_el.get_text(strip=True)

        print(f"[BWF Login] Player name from masthead: {player_name}")

        # Search by last name to get license ID and club, matching by profile URL
        if player_name and profile_url:
            search_query = player_name.split()[-1]
            search_resp = s.get(
                "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
                params={"Page": 1, "SportID": 2, "Query": search_query},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=10
            )
            search_soup = BeautifulSoup(search_resp.text, "html.parser")

            for item in search_soup.select("li.list__item"):
                item_link = item.select_one("a.media__link")
                if item_link and item_link.get("href", "").lower() == profile_url.lower():
                    license_el = item.select_one(".media__title-aside")
                    if license_el:
                        license_id = license_el.get_text(strip=True).strip("()")
                    club_el = item.select_one(".media__subheading span.nav-link__value")
                    if club_el:
                        club = club_el.get_text(strip=True).split("|")[0].strip()
                    break

        # Fetch gender, email, phone, date of birth from account settings
        gender = ""
        email = ""
        phone = ""
        dob = ""
        age = ""
        try:
            settings_resp = s.get("https://badmintonsweden.tournamentsoftware.com/user/account-settings/person", timeout=10)
            settings_soup = BeautifulSoup(settings_resp.text, "html.parser")
            for dt in settings_soup.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue
                label = dt.get_text(strip=True).rstrip(":")
                value = dd.get_text(strip=True)
                if label == "Kön":
                    gender = "F" if "kvinna" in value.lower() else "M" if "man" in value.lower() else ""
                elif label == "E-mail":
                    email = value.replace("(Redigera)", "").strip()
                elif label == "Telefon (mobil)" and value:
                    phone = value
                elif label == "Phone 3" and value and not phone:
                    phone = value
                elif "Födelsedatum" in label and value:
                    dob = value.split(" ")[0]
                    try:
                        from datetime import datetime as dt_cls
                        birth = dt_cls.strptime(dob, "%Y-%m-%d")
                        today = dt_cls.now()
                        age = str(today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day)))
                    except Exception:
                        pass
        except Exception:
            pass

        # Fetch ranking data from player profile
        ranking = {}
        try:
            ranking_resp = s.get(f"https://badmintonsweden.tournamentsoftware.com{profile_url}/ranking", timeout=10)
            ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
            table = ranking_soup.find("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    th = row.find("th", scope="row")
                    tds = row.find_all("td")
                    if th and len(tds) >= 2:
                        category = th.get_text(strip=True)
                        if category:
                            ranking[category] = {"rank": tds[0].get_text(strip=True), "points": tds[1].get_text(strip=True)}
        except Exception:
            pass

        print(f"[BWF Login] Final: name={player_name}, license={license_id}, club={club}, gender={gender}, email={email}, phone={phone}")
        print(f"[BWF Login] Ranking: {ranking}")

        if not player_name:
            player_name = login

        session["bwf_player"] = player_name
        session["bwf_login"] = login
        session["bwf_license_id"] = license_id
        session["bwf_club"] = club
        session["bwf_gender"] = gender
        session["bwf_email"] = email
        session["bwf_phone"] = phone
        session["bwf_dob"] = dob
        session["bwf_age"] = age
        session["bwf_ranking"] = ranking
        session["admin"] = is_admin_user(login)
        
        # Save player data to players.db (we have ALL fields from login)
        try:
            if license_id:
                from players_scraper import update_player_in_db
                
                ranking_json = json.dumps(ranking) if ranking else None
                update_player_in_db(
                    license_id=license_id,
                    name=player_name,
                    profile_url=profile_url,
                    club=club,
                    gender=gender,
                    email=email,
                    phone=phone,
                    dob=dob,
                    age=age,
                    ranking=ranking_json
                )
                logger.info(f"✅ Saved full player data for {player_name} ({license_id}) to players.db")
        except Exception as e:
            logger.warning(f"⚠️  Could not save player data to DB: {e}")
        
        return jsonify(success=True, player_name=player_name, license_id=license_id, club=club, gender=gender, email=email, phone=phone, dob=dob, age=age, ranking=ranking)

    except ext_requests.RequestException as e:
        return jsonify(success=False, error=f"Connection error: {str(e)}"), 500


@app.route("/api/bwf-logout", methods=["POST"])
def bwf_logout():
    session.clear()
    return jsonify(success=True)


@app.route("/api/bwf-status", methods=["GET"])
def bwf_status():
    player = session.get("bwf_player")
    license_id = session.get("bwf_license_id", "")
    club = session.get("bwf_club", "")
    gender = session.get("bwf_gender", "")
    email = session.get("bwf_email", "")
    phone = session.get("bwf_phone", "")
    dob = session.get("bwf_dob", "")
    age = session.get("bwf_age", "")
    ranking = session.get("bwf_ranking", {})
    is_admin = session.get("admin", False)
    return jsonify(logged_in=bool(player), player_name=player or "", license_id=license_id, club=club, gender=gender, email=email, phone=phone, dob=dob, age=age, ranking=ranking, is_admin=is_admin)

@app.route("/api/validate-registration", methods=["POST"])
def validate_registration():
    """Check if player's points and age allow them to register for a given level."""
    data = request.json
    level = data.get("level", "").strip()
    category = data.get("category", "")  # HS, DS, HD, DD, MD
    points = data.get("points")  # player's points for that category
    age = data.get("age")  # player's age
    dob = data.get("dob", "")  # player's date of birth
    competition_date = data.get("competition_date", "")  # tournament competition start date

    if not level or not category:
        return jsonify(success=True, allowed=True)

    # Age-based levels (U9, U11, U13, U15, U17, U19)
    # Player must be UNDER that age to play
    # e.g., U13 means player must be under 13 (12 or younger)
    # Exception: player can play their age group until June of the year they age out
    if level.startswith("U") and dob:
        try:
            import re
            age_limit = int(re.search(r'\d+', level).group())
            from datetime import datetime as dt_cls
            birth = dt_cls.strptime(dob, "%Y-%m-%d")

            check_date = dt_cls.now()
            if competition_date:
                try:
                    check_date = dt_cls.strptime(competition_date, "%Y-%m-%d")
                except Exception:
                    pass

            # Year they turn the age limit
            year_turn_limit = birth.year + age_limit

            # Age at competition
            age_at_comp = check_date.year - birth.year - ((check_date.month, check_date.day) < (birth.month, birth.day))

            # Player is too old for this category
            if age_at_comp >= age_limit:
                # Exception: can still play until June of the year they age out
                if check_date.year == year_turn_limit and check_date.month <= 6:
                    pass  # Allowed - still within grace period
                else:
                    return jsonify(success=True, allowed=False, hard_block=True,
                        message=f"Player is {age_at_comp} years old. {level} is for players under {age_limit}. NOT ALLOWED.")

            # Player is too young - can't play a lower age group
            # e.g., a 12-year-old can't play U9 or U11
            if age_at_comp >= age_limit:
                pass  # Already handled above
            elif age_limit - age_at_comp > 2:
                # Player is way younger than the category - that's fine (playing up)
                pass
            # Check if player should be in a higher age group
            # A 12-year-old should play U13, not U9 or U11
            age_groups = [9, 11, 13, 15, 17, 19]
            correct_group = None
            for ag in age_groups:
                if age_at_comp < ag:
                    correct_group = ag
                    break
            if correct_group and age_limit < correct_group and age_at_comp >= age_limit:
                return jsonify(success=True, allowed=False, hard_block=True,
                    message=f"Player is {age_at_comp} years old. Cannot play {level} (too old). Should play U{correct_group} or higher.")

        except Exception:
            pass

        # No point restrictions for age-based levels
        return jsonify(success=True, allowed=True)

    if level.startswith("U"):
        return jsonify(success=True, allowed=True)

    # Adult classes: Elit, A, B, C, D
    # Junior rules for senior categories:
    # - Under 13: can play B, A, Elit with special permission (dispens) — NOT C or D
    # - Under 18 (junior): can play B, A, Elit — NOT C or D
    # - C and D classes are for seniors (18+) only
    adult_classes = {"Elit", "A", "B", "C", "D"}
    if level in adult_classes and dob:
        try:
            from datetime import datetime as dt_cls
            birth = dt_cls.strptime(dob, "%Y-%m-%d")
            today = dt_cls.now()

            # Year they turn 13
            year_turn_13 = birth.year + 13

            # Competition date or today for checking
            check_date = today
            if competition_date:
                try:
                    check_date = dt_cls.strptime(competition_date, "%Y-%m-%d")
                except Exception:
                    pass

            # Calculate age at competition date
            age_at_comp = check_date.year - birth.year - ((check_date.month, check_date.day) < (birth.month, birth.day))

            # HARD BLOCK: Under 18 cannot play C or D class (seniors only)
            if age_at_comp < 18 and level in {"C", "D"}:
                return jsonify(success=True, allowed=False, hard_block=True,
                    message=f"Player is {age_at_comp} years old. {level} class is for seniors (18+) only. Juniors can only play B, A, or Elit.")

            # WARNING: Under 13 needs special permission for any senior class (B, A, Elit)
            if age_at_comp < 13:
                return jsonify(success=True, allowed=False, age_restriction=True,
                    message=f"Player must be at least 13 years old to play {level} class. Current age: {age_at_comp}")

            # If turning 13 this year, can only play after June
            if check_date.year == year_turn_13 and check_date.month < 6:
                return jsonify(success=True, allowed=False, age_restriction=True,
                    message=f"Player turns 13 in {year_turn_13}. Can only play adult classes ({level}) after June {year_turn_13}.")

        except Exception:
            pass

    # Point validation
    conn = sqlite3.connect(POINTS_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM point_rules WHERE klass=?", (level,))
    rule = cur.fetchone()
    conn.close()

    if not rule:
        return jsonify(success=True, allowed=True)

    col_min = f"{category.lower()}_min"
    col_max = f"{category.lower()}_max"
    min_pts = rule[col_min]
    max_pts = rule[col_max]

    if points is None:
        return jsonify(success=True, allowed=True, warning="No ranking data available to validate.")

    points = int(points)
    blocked = False
    message = ""

    if min_pts is not None and points < min_pts:
        blocked = True
        message = f"Your {category} points ({points}) are below the minimum ({min_pts}) for class {level}."
        return jsonify(success=True, allowed=False, hard_block=False, message=message)
    elif max_pts is not None and points > max_pts:
        blocked = True
        message = f"Your {category} points ({points}) exceed the maximum ({max_pts}) for class {level}. Not allowed to play this category."
        return jsonify(success=True, allowed=False, hard_block=True, message=message)

    return jsonify(success=True, allowed=True)


@app.route("/api/tournament-warnings", methods=["GET"])
def get_tournament_warnings():
    """Check all registrations in a tournament for age/point violations.
    Returns warnings for admin view and per-player warnings."""
    tournament_name = request.args.get("dbFile", "").strip()
    license_id_filter = request.args.get("license_id", "").strip()  # Optional: filter for specific player
    
    if not tournament_name:
        return jsonify(success=True, warnings=[])
    
    try:
        # Get tournament competition date
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        cur.execute("SELECT competition_start FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        row = cur.fetchone()
        competition_date = row[0] if row else ""
        
        # Get all registrations
        query = """
            SELECT tr.license_id, tr.singles_levels, tr.doubles_levels, tr.mixed_levels
            FROM tournament_registrations tr
            WHERE tr.tournament_name = ?
        """
        params = [tournament_name]
        if license_id_filter:
            query += " AND tr.license_id = ?"
            params.append(license_id_filter)
        
        cur.execute(query, params)
        registrations = cur.fetchall()
        conn.close()
        
        # Get point rules
        conn_rules = sqlite3.connect(POINTS_DB)
        conn_rules.row_factory = sqlite3.Row
        cur_rules = conn_rules.cursor()
        cur_rules.execute("SELECT * FROM point_rules")
        all_rules = {row["klass"]: dict(row) for row in cur_rules.fetchall()}
        conn_rules.close()
        
        # Get player data (name, dob, ranking) from players.db
        conn_players = sqlite3.connect(PLAYERS_DB)
        cur_players = conn_players.cursor()
        
        warnings = []
        
        for reg in registrations:
            reg_license_id = reg[0]
            singles_levels = reg[1] or ""
            doubles_levels = reg[2] or ""
            mixed_levels = reg[3] or ""
            
            # Get player info
            cur_players.execute("SELECT name, dob, age, ranking FROM players WHERE license_id = ?", (reg_license_id,))
            player_row = cur_players.fetchone()
            if not player_row:
                continue
            
            player_name = player_row[0] or "Unknown"
            player_dob = player_row[1] or ""
            player_age = player_row[2] or ""
            player_ranking_json = player_row[3] or ""
            
            try:
                player_ranking = json.loads(player_ranking_json) if player_ranking_json else {}
                # Handle double-encoded JSON
                if isinstance(player_ranking, str):
                    player_ranking = json.loads(player_ranking)
            except Exception:
                player_ranking = {}
            
            # Check each registered category
            all_levels = []
            if singles_levels:
                for lvl in singles_levels.split(","):
                    lvl = lvl.strip()
                    if lvl:
                        parts = lvl.split(" ", 1)
                        all_levels.append({"event": lvl, "category": parts[0], "level": parts[1] if len(parts) > 1 else ""})
            if doubles_levels:
                for lvl in doubles_levels.split(","):
                    lvl = lvl.strip()
                    if lvl:
                        parts = lvl.split(" ", 1)
                        all_levels.append({"event": lvl, "category": parts[0], "level": parts[1] if len(parts) > 1 else ""})
            if mixed_levels:
                for lvl in mixed_levels.split(","):
                    lvl = lvl.strip()
                    if lvl:
                        parts = lvl.split(" ", 1)
                        all_levels.append({"event": lvl, "category": parts[0], "level": parts[1] if len(parts) > 1 else ""})
            
            for entry in all_levels:
                category = entry["category"]
                level = entry["level"]
                event = entry["event"]
                
                if not level:
                    continue
                
                # Age check for adult classes
                adult_classes = {"Elit", "A", "B", "C", "D"}
                if level in adult_classes and player_dob:
                    try:
                        from datetime import datetime as dt_cls
                        birth = dt_cls.strptime(player_dob, "%Y-%m-%d")
                        check_date = dt_cls.now()
                        if competition_date:
                            try:
                                check_date = dt_cls.strptime(competition_date, "%Y-%m-%d")
                            except Exception:
                                pass
                        
                        year_turn_13 = birth.year + 13
                        age_at_comp = check_date.year - birth.year - ((check_date.month, check_date.day) < (birth.month, birth.day))
                        
                        # HARD BLOCK: Under 18 cannot play C or D (seniors only)
                        if age_at_comp < 18 and level in {"C", "D"}:
                            warnings.append({
                                "license_id": reg_license_id,
                                "player_name": player_name,
                                "type": "points_high",
                                "event": event,
                                "message": f"{player_name} is {age_at_comp} years old. {level} class is for seniors (18+) only."
                            })
                            continue
                        
                        if age_at_comp < 13:
                            warnings.append({
                                "license_id": reg_license_id,
                                "player_name": player_name,
                                "type": "age",
                                "event": event,
                                "message": f"{player_name} is {age_at_comp} years old. Must be at least 13 to play {level} class."
                            })
                            continue  # Skip point check if age is already an issue
                        
                        if check_date.year == year_turn_13 and check_date.month < 6:
                            warnings.append({
                                "license_id": reg_license_id,
                                "player_name": player_name,
                                "type": "age",
                                "event": event,
                                "message": f"{player_name} turns 13 in {year_turn_13}. Can only play {level} class after June {year_turn_13}."
                            })
                            continue
                    except Exception:
                        pass
                
                # Point check for adult classes
                if level in adult_classes:
                    rule = all_rules.get(level)
                    if rule:
                        col_min = f"{category.lower()}_min"
                        col_max = f"{category.lower()}_max"
                        min_pts = rule.get(col_min)
                        max_pts = rule.get(col_max)
                        
                        cat_ranking = player_ranking.get(category, {})
                        points_str = cat_ranking.get("points", "")
                        if points_str:
                            try:
                                points = int(points_str)
                                if min_pts is not None and points < min_pts:
                                    warnings.append({
                                        "license_id": reg_license_id,
                                        "player_name": player_name,
                                        "type": "points_low",
                                        "event": event,
                                        "message": f"{player_name}: {category} points ({points}) below minimum ({min_pts}) for {level} class."
                                    })
                                elif max_pts is not None and points > max_pts:
                                    warnings.append({
                                        "license_id": reg_license_id,
                                        "player_name": player_name,
                                        "type": "points_high",
                                        "event": event,
                                        "message": f"{player_name}: {category} points ({points}) exceed maximum ({max_pts}) for {level} class. NOT ALLOWED."
                                    })
                            except ValueError:
                                pass
        
        conn_players.close()
        return jsonify(success=True, warnings=warnings)
    
    except Exception as e:
        logger.error(f"❌ Error checking tournament warnings: {e}")
        return jsonify(success=True, warnings=[])


@app.route("/api/admin-exists", methods=["GET"])
def admin_exists():
    return jsonify(exists=True)


@app.route("/admin/add-admin-by-id", methods=["POST"])
def add_admin_by_id():
    """Add admin by username and email (admin-only operation, no verification)"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    if not username:
        return jsonify(success=False, error="Username required"), 400
    
    # Add as admin
    conn = sqlite3.connect(ADMIN_DB)
    try:
        conn.execute("INSERT INTO admin_users (username, email) VALUES (?, ?)", (username, email or None))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify(success=False, error="User is already an admin")
    conn.close()
    return jsonify(success=True)


@app.route("/admin/add-admin", methods=["POST"])
def add_admin():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    if not username or not password:
        return jsonify(success=False, error="Username and password required"), 400
    if confirm_password != "admin@2026":
        return jsonify(success=False, error="Incorrect admin confirmation password"), 403

    # Verify user against Badminton Sweden
    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/user",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=10)
        resp = s.get("https://badmintonsweden.tournamentsoftware.com/user", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        token_el = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_el:
            return jsonify(success=False, error="Could not connect to Badminton Sweden"), 500
        logo_el = soup.find("input", {"name": "LogoUrl"})
        resp = s.post("https://badmintonsweden.tournamentsoftware.com/user", data={
            "__RequestVerificationToken": token_el.get("value", ""),
            "ReturnUrl": "/",
            "LogoUrl": logo_el.get("value", "") if logo_el else "",
            "Login": username,
            "Password": password
        }, allow_redirects=True, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find("input", {"name": "Login"}):
            return jsonify(success=False, error="Invalid Badminton Sweden credentials"), 401
    except ext_requests.RequestException as e:
        return jsonify(success=False, error=f"Connection error: {str(e)}"), 500

    # Verified - add as admin
    conn = sqlite3.connect(ADMIN_DB)
    try:
        conn.execute("INSERT INTO admin_users (username) VALUES (?)", (username,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify(success=False, error="User is already an admin")
    conn.close()
    # If user just added themselves, update session
    if username == session.get("bwf_login"):
        session["admin"] = True
    return jsonify(success=True)


@app.route("/admin/remove-admin", methods=["POST"])
def remove_admin():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    username = data.get("username", "").strip()
    if not username:
        return jsonify(success=False, error="Username required"), 400
    conn = sqlite3.connect(ADMIN_DB)
    conn.execute("DELETE FROM admin_users WHERE username=?", (username,))
    conn.commit()
    conn.close()
    # If removed self, update session
    if username == session.get("bwf_login"):
        session["admin"] = False
    return jsonify(success=True)


@app.route("/admin/list-admins", methods=["GET"])
def list_admins():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT username FROM admin_users ORDER BY username")
    admins = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify(success=True, admins=admins)


@app.route("/api/list-admins", methods=["GET"])
def api_list_admins():
    """API endpoint for listing admins (used by manage-admins page)"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT username, email FROM admin_users ORDER BY username")
    admins = [{"username": row[0], "email": row[1] or ""} for row in cur.fetchall()]
    conn.close()
    return jsonify(success=True, admins=admins)


@app.route("/api/remove-admin", methods=["POST"])
def api_remove_admin():
    """API endpoint for removing an admin (used by manage-admins page)"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    username = data.get("username", "").strip()
    if not username:
        return jsonify(success=False, error="Username required"), 400
    conn = sqlite3.connect(ADMIN_DB)
    conn.execute("DELETE FROM admin_users WHERE username=?", (username,))
    conn.commit()
    conn.close()
    if username == session.get("bwf_login"):
        session["admin"] = False
    return jsonify(success=True)


@app.route("/api/point-rules", methods=["GET"])
def get_point_rules():
    conn = sqlite3.connect(POINTS_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM point_rules ORDER BY id")
    rules = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(success=True, rules=rules)


@app.route("/admin/update-point-rules", methods=["POST"])
def update_point_rules():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    rules = data.get("rules", [])
    conn = sqlite3.connect(POINTS_DB)
    for rule in rules:
        conn.execute(
            "UPDATE point_rules SET hs_min=?, hs_max=?, ds_min=?, ds_max=?, hd_min=?, hd_max=?, dd_min=?, dd_max=?, md_min=?, md_max=? WHERE id=?",
            (rule.get("hs_min"), rule.get("hs_max"), rule.get("ds_min"), rule.get("ds_max"),
             rule.get("hd_min"), rule.get("hd_max"), rule.get("dd_min"), rule.get("dd_max"),
             rule.get("md_min"), rule.get("md_max"), rule["id"])
        )
    conn.commit()
    conn.close()
    trigger_sync()  # Trigger debounced sync after database change
    return jsonify(success=True)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify(success=True)


@app.route("/api/smtp-settings", methods=["GET"])
def get_smtp_settings():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    conn = sqlite3.connect(ADMIN_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM smtp_settings WHERE id=1")
    row = cur.fetchone()
    conn.close()
    if row:
        return jsonify(success=True, settings={
            "smtp_host": row["smtp_host"],
            "smtp_port": row["smtp_port"],
            "smtp_email": row["smtp_email"],
            "smtp_password": "********" if row["smtp_password"] else "",
            "reminder_days": row["reminder_days"]
        })
    return jsonify(success=True, settings={"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_email": "", "smtp_password": "", "reminder_days": 3})


@app.route("/admin/save-smtp-settings", methods=["POST"])
def save_smtp_settings():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM smtp_settings WHERE id=1")
    existing = cur.fetchone()

    smtp_password = data.get("smtp_password", "")
    # Don't overwrite password if it's the masked value
    if smtp_password == "********":
        cur.execute("SELECT smtp_password FROM smtp_settings WHERE id=1")
        row = cur.fetchone()
        smtp_password = row[0] if row else ""

    if existing:
        conn.execute(
            "UPDATE smtp_settings SET smtp_host=?, smtp_port=?, smtp_email=?, smtp_password=?, reminder_days=? WHERE id=1",
            (data.get("smtp_host", "smtp.gmail.com"), data.get("smtp_port", 587),
             data.get("smtp_email", ""), smtp_password, data.get("reminder_days", 3))
        )
    else:
        conn.execute(
            "INSERT INTO smtp_settings (id, smtp_host, smtp_port, smtp_email, smtp_password, reminder_days) VALUES (1,?,?,?,?,?)",
            (data.get("smtp_host", "smtp.gmail.com"), data.get("smtp_port", 587),
             data.get("smtp_email", ""), smtp_password, data.get("reminder_days", 3))
        )
    conn.commit()
    conn.close()
    trigger_sync()  # Sync SMTP settings to Dropbox
    return jsonify(success=True)


@app.route("/admin/send-test-email", methods=["POST"])
def send_test_email():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    to_email = data.get("to_email", "")
    if not to_email:
        return jsonify(success=False, error="Email required"), 400

    result = send_email(to_email, "Test Email - Badminton Tournament", "This is a test email from your Badminton Tournament system.")
    if result is True:
        return jsonify(success=True, message="Test email sent!")
    return jsonify(success=False, error=result if isinstance(result, str) else "Unknown error")


# --- Tournament CRUD ---
@app.route("/api/tournaments", methods=["GET"])
def list_tournaments():
    """List tournaments that have registrations from tournament_registrations table"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Get distinct tournament_names from registrations, with their data
        cur.execute("""
            SELECT DISTINCT tr.tournament_name, 
                   t.tournament_name,
                   t.location,
                   t.date_start,
                   t.date_end
            FROM tournament_registrations tr
            LEFT JOIN tournaments t ON tr.tournament_name = t.tournament_name
            ORDER BY COALESCE(t.date_start, '')
        """)
        
        tournaments = []
        for row in cur.fetchall():
            tournament_name = row[0]
            
            # Get registration count for this tournament
            cur.execute(
                "SELECT COUNT(*) FROM tournament_registrations WHERE tournament_name = ?",
                (tournament_name,)
            )
            reg_count = cur.fetchone()[0]
            
            tournaments.append({
                "id": tournament_name,
                "db": tournament_name,  # Now tournament_name
                "name": row[1] or tournament_name,
                "tournament_name": row[1] or tournament_name,
                "location": row[2] or "",
                "date_start": row[3] or "",
                "date_end": row[4] or "",
                "competition_date": row[3] or "",
                "final_registration_date": row[4] or "",
                "registrations": reg_count
            })
        
        conn.close()
        return jsonify(tournaments)
    except Exception as e:
        logger.error(f"❌ Error listing tournaments: {e}")
        return jsonify([])


@app.route("/admin/search-tournaments", methods=["GET"])
def search_tournaments_bwf():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    try:
        from datetime import datetime, timedelta
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        start = datetime.now().strftime("%Y-%m-%dT00:00")
        end = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%dT00:00")

        # Load the find page to get form data
        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/find?StatusFilterID=2&DateFilterType=0&StartDate={start}&EndDate={end}&Distance=10&page=1&SportID=2", timeout=10)
        page_soup = BeautifulSoup(resp.text, "html.parser")
        form = page_soup.select_one("#form_globalsearch")
        form_data = {}
        if form:
            for inp in form.find_all("input"):
                name = inp.get("name", "")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value

        # Set StatusFilterID to 2 for 'Online-anmälan öppen' (registration open)
        form_data["TournamentExtendedFilter.StatusFilterID"] = "2"

        # POST to get results
        resp = s.post("https://badmintonsweden.tournamentsoftware.com/find/tournament/DoSearch",
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        tournaments = []
        for item in soup.select("li.list__item"):
            link = item.select_one("a.media__link")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href", "")
            # Get location
            location_el = item.select_one(".media__subheading .nav-link__value")
            location = location_el.get_text(strip=True) if location_el else ""
            # Get dates
            time_els = item.select("time")
            date_start = time_els[0].get("datetime", "")[:10] if time_els else ""
            date_end = time_els[1].get("datetime", "")[:10] if len(time_els) > 1 else ""
            # Build full URL
            import re
            tid_match = re.search(r'id=([A-Fa-f0-9-]+)', href)
            tournament_url = f"https://badmintonsweden.tournamentsoftware.com/tournament/{tid_match.group(1)}" if tid_match else ""

            tournaments.append({
                "name": name,
                "url": tournament_url,
                "location": location,
                "date_start": date_start,
                "date_end": date_end
            })

        return jsonify(success=True, tournaments=tournaments)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/admin/fetch-tournament-info", methods=["POST"])
def fetch_tournament_info():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify(success=False, error="URL required"), 400

    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        # Fetch tournament page
        resp = s.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Get tournament name
        name = ""
        name_el = soup.select_one(".media__title a")
        if name_el:
            name = name_el.get_text(strip=True)
        if not name:
            name_el = soup.select_one(".media__title")
            if name_el:
                name = name_el.get_text(strip=True)

        # Get timeline dates
        dates = {}
        timeline = soup.select_one(".tournament-meta__timeline")
        if timeline:
            for li in timeline.find_all("li"):
                label_el = li.select_one(".list__value")
                time_el = li.find("time")
                if label_el and time_el:
                    label = label_el.get_text(strip=True)
                    datetime_val = time_el.get("datetime", "")[:10]  # Get YYYY-MM-DD
                    if "öppnar" in label.lower():
                        dates["registration_opens"] = datetime_val
                    elif "stänger" in label.lower():
                        dates["registration_closes"] = datetime_val
                    elif "återbud" in label.lower():
                        dates["cancellation_deadline"] = datetime_val
                    elif "start" in label.lower():
                        dates["competition_start"] = datetime_val
                    elif "slut" in label.lower():
                        dates["competition_end"] = datetime_val

        # Get levels from events page
        levels = []
        # Extract tournament ID from URL
        import re
        tid_match = re.search(r'/tournament/([^/]+)', url)
        if tid_match:
            tid = tid_match.group(1)
            events_resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/sport/events.aspx?id={tid}", timeout=10)
            events_soup = BeautifulSoup(events_resp.text, "html.parser")
            level_set = set()
            for a in events_soup.select("a"):
                text = a.get_text(strip=True)
                if text and len(text) < 50 and any(cat in text for cat in ["HS", "DS", "HD", "DD", "MD", "PS", "FS", "PD", "FD"]):
                    parts = text.split()
                    if len(parts) >= 2:
                        level_set.add(parts[1])
            levels = sorted(level_set)

        return jsonify(
            success=True,
            name=name,
            levels=levels,
            registration_opens=dates.get("registration_opens", ""),
            registration_closes=dates.get("registration_closes", ""),
            cancellation_deadline=dates.get("cancellation_deadline", ""),
            competition_start=dates.get("competition_start", ""),
            competition_end=dates.get("competition_end", "")
        )
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/admin/create-tournament", methods=["POST"])
def create_tournament():
    """Manual tournament creation deprecated - tournaments are synced from Badminton Sweden"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    return jsonify(
        success=False, 
        error="Manual tournament creation is deprecated.",
        message="Tournaments are automatically synced from Badminton Sweden. Use the Manage Tournaments tab to select tournaments."
    ), 400


@app.route("/admin/delete-tournament", methods=["POST"])
def delete_tournament():
    """Manual tournament deletion deprecated"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    return jsonify(
        success=False,
        error="Manual tournament deletion is deprecated.",
        message="Deselect tournaments in the Manage Tournaments tab instead."
    ), 400


@app.route("/admin/submit-tournament", methods=["POST"])
def submit_tournament():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    # TODO: Implement actual submission to Badminton Sweden
    return jsonify(success=True, message="Submit functionality will be implemented later.")


@app.route("/admin/edit-tournament", methods=["POST"])
def edit_tournament():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    db_file = data.get("db")
    if not db_file:
        return jsonify(success=False, error="db required"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404

    conn.execute(
        "UPDATE tournaments SET name=?, levels=?, competition_date=?, final_registration_date=?, final_cancellation_date=?",
        (data.get("name", ""), json.dumps(data.get("levels", [])),
         data.get("competition_date", ""), data.get("final_registration_date", ""),
         data.get("final_cancellation_date", ""))
    )
    conn.commit()
    conn.close()
    trigger_sync()  # Sync tournament changes to Dropbox
    return jsonify(success=True)


@app.route("/api/tournament-visibility", methods=["GET"])
def get_tournament_visibility():
    """Get list of all tournaments and their visibility status"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    logger.info("📋 Admin viewing tournament visibility")
    
    # Get all tournaments from unified tournaments.db
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tournament_name, location, date_start, date_end, selected_for_view
            FROM tournaments
            ORDER BY date_start DESC
        """)
        
        tournaments = []
        for row in cur.fetchall():
            tournaments.append({
                "id": row[0],
                "name": row[1],
                "location": row[2],
                "date_start": row[3],
                "date_end": row[4],
                "visible": row[5]
            })
        
        conn.close()
        logger.info(f"✅ Retrieved {len(tournaments)} tournaments for visibility view")
        return jsonify(success=True, tournaments=tournaments)
    
    except Exception as e:
        logger.error(f"❌ Error fetching tournament visibility: {str(e)}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/tournament-visibility/toggle", methods=["POST"])
def toggle_tournament_visibility():
    """Toggle tournament visibility for available tournaments list"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    db_file = data.get("db")
    if not db_file:
        return jsonify(success=False, error="db required"), 400
    
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    
    # Get current visibility
    cur.execute("SELECT id, visible FROM tournament_visibility WHERE tournament_db=?", (db_file,))
    row = cur.fetchone()
    
    if row:
        # Update existing
        new_visible = 1 - row[1]
        cur.execute("UPDATE tournament_visibility SET visible=? WHERE tournament_db=?", (new_visible, db_file))
    else:
        # Create new entry
        conn.execute(
            "INSERT INTO tournament_visibility (tournament_db, visible) VALUES (?, ?)",
            (db_file, 1)
        )
    
    conn.commit()
    conn.close()
    trigger_sync()
    return jsonify(success=True)


@app.route("/api/tournament-reg-date", methods=["POST"])
def set_tournament_reg_date():
    """Set admin_reg_end_date for a tournament"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    tournament_name = data.get("tournament_name", "").strip()
    admin_reg_end_date = data.get("admin_reg_end_date", "").strip()
    
    if not tournament_name:
        return jsonify(success=False, error="Tournament name required")
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute(
            "UPDATE tournaments SET admin_reg_end_date = ? WHERE tournament_name = ?",
            (admin_reg_end_date or None, tournament_name)
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ Set admin_reg_end_date={admin_reg_end_date} for {tournament_name}")
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/tournament-groups", methods=["POST"])
def set_tournament_groups():
    """Set groups for a tournament (stored as JSON array)"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    tournament_name = data.get("tournament_name", "").strip()
    groups = data.get("groups", [])
    
    if not tournament_name:
        return jsonify(success=False, error="Tournament name required")
    
    groups_json = json.dumps(groups) if groups else None
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute(
            "UPDATE tournaments SET tournament_groups = ? WHERE tournament_name = ?",
            (groups_json, tournament_name)
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ Set tournament_groups={groups} for {tournament_name}")
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/bwf-tournament-visibility/save", methods=["POST"])
def save_bwf_tournament_visibility():
    """Save selected tournaments - toggle selected_for_view in tournaments.db"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    selected_tournaments = data.get("tournaments", [])  # Array of tournament objects with URLs
    
    logger.info(f"Received request to save {len(selected_tournaments)} tournaments")
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Get URLs of selected tournaments
    selected_urls = {t.get("url") for t in selected_tournaments}
    
    # Set selected_for_view=1 for selected tournaments
    for t in selected_tournaments:
        try:
            cur.execute("""
                UPDATE tournaments 
                SET selected_for_view = 1, last_updated = CURRENT_TIMESTAMP
                WHERE tournament_url = ?
            """, (t.get("url"),))
            logger.debug(f"Marked as selected: {t.get('name')}")
        except Exception as e:
            logger.error(f"Error updating tournament {t.get('url')}: {e}")
    
    # Set selected_for_view=0 for unselected tournaments
    try:
        placeholders = ','.join(['?' for _ in selected_urls])
        if placeholders:
            cur.execute(f"""
                UPDATE tournaments 
                SET selected_for_view = 0, last_updated = CURRENT_TIMESTAMP
                WHERE tournament_url NOT IN ({placeholders})
            """, list(selected_urls))
            logger.debug(f"Marked as unselected: non-selected tournaments")
        else:
            # If nothing selected, unselect all
            cur.execute("UPDATE tournaments SET selected_for_view = 0, last_updated = CURRENT_TIMESTAMP")
            logger.debug("Unselected all tournaments")
    except Exception as e:
        logger.error(f"Error updating unselected tournaments: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Successfully saved {len(selected_tournaments)} tournaments")
    trigger_sync()
    return jsonify(success=True)


@app.route("/api/bwf-tournaments-all", methods=["GET"])
def get_all_bwf_tournaments():
    """Get ALL tournaments from Badminton Sweden and store in tournaments.db"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    force_refresh = request.args.get("force", "false") == "true"
    
    try:
        from datetime import datetime, timedelta
        
        # CHECK CACHE: If already fetched today, return from DB (unless force refresh)
        if not force_refresh:
            conn_cache = sqlite3.connect(TOURNAMENTS_DB)
            cur_cache = conn_cache.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            cur_cache.execute("SELECT COUNT(*) FROM tournaments WHERE last_updated LIKE ?", (f"{today}%",))
            fetched_today = cur_cache.fetchone()[0]
            
            if fetched_today > 0:
                # Already fetched today - return cached data
                cur_cache.execute("SELECT tournament_url, tournament_name, location, date_start, date_end, selected_for_view, registration_closes, tournament_groups, categories FROM tournaments ORDER BY date_start")
                tournaments_cached = []
                for row in cur_cache.fetchall():
                    tg = []
                    try:
                        tg = json.loads(row[7]) if row[7] else []
                    except Exception:
                        pass
                    cats = {}
                    try:
                        cats = json.loads(row[8]) if row[8] else {}
                    except Exception:
                        pass
                    tournaments_cached.append({
                        "url": row[0],
                        "name": row[1],
                        "location": row[2],
                        "date_start": row[3],
                        "date_end": row[4],
                        "selected_for_view": row[5],
                        "registration_closes": row[6] or "",
                        "admin_reg_end_date": "",
                        "tournament_groups": tg,
                        "categories": cats
                    })
                conn_cache.close()
                logger.info(f"✅ Returning {len(tournaments_cached)} cached tournaments (already fetched today)")
                return jsonify(success=True, tournaments=tournaments_cached, cached=True)
            conn_cache.close()
        
        logger.info("🔄 Fetching fresh tournament data from Badminton Sweden...")
        
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        start = datetime.now().strftime("%Y-%m-%dT00:00")
        end = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%dT00:00")

        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/find?StatusFilterID=2&DateFilterType=0&StartDate={start}&EndDate={end}&Distance=10&page=1&SportID=2", timeout=10)
        page_soup = BeautifulSoup(resp.text, "html.parser")
        form = page_soup.select_one("#form_globalsearch")
        form_data = {}
        if form:
            for inp in form.find_all("input"):
                name = inp.get("name", "")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value
        form_data["TournamentExtendedFilter.StatusFilterID"] = "2"

        resp = s.post("https://badmintonsweden.tournamentsoftware.com/find/tournament/DoSearch",
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        tournaments = []
        import re
        for item in soup.select("li.list__item"):
            link = item.select_one("a.media__link")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href", "")
            location_el = item.select_one(".media__subheading .nav-link__value")
            location = location_el.get_text(strip=True) if location_el else ""
            time_els = item.select("time")
            date_start = time_els[0].get("datetime", "")[:10] if time_els else ""
            date_end = time_els[1].get("datetime", "")[:10] if len(time_els) > 1 else ""
            tid_match = re.search(r'id=([A-Fa-f0-9-]+)', href)
            tournament_url = f"https://badmintonsweden.tournamentsoftware.com/tournament/{tid_match.group(1)}" if tid_match else ""

            tournaments.append({
                "name": name,
                "url": tournament_url,
                "location": location,
                "date_start": date_start,
                "date_end": date_end
            })

        logger.info(f"Found {len(tournaments)} tournaments from Badminton Sweden")
        
        # STEP 1: Get current tournaments to preserve selected_for_view
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        cur.execute("SELECT tournament_name, selected_for_view FROM tournaments")
        selection_map = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        
        # STEP 2: For each tournament, extract complete date details and categories
        # Uses ThreadPoolExecutor for parallel fetching (5 concurrent requests)
        logger.info(f"📝 Processing {len(tournaments)} tournaments in parallel...")
        added_count = 0
        updated_count = 0
        
        def fetch_tournament_details(t):
            """Fetch dates and categories for a single tournament (thread-safe)"""
            try:
                # Create per-thread session (sharing session across threads is unsafe)
                ts = ext_requests.Session()
                ts.headers.update({"User-Agent": "Mozilla/5.0"})
                ts.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
                    "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
                }, allow_redirects=True, timeout=5)
                
                resp_detail = ts.get(t["url"], timeout=10)
                soup_detail = BeautifulSoup(resp_detail.text, "html.parser")
                
                # Extract detailed dates
                dates = {}
                timeline = soup_detail.select_one(".tournament-meta__timeline")
                if timeline:
                    for li in timeline.find_all("li"):
                        label_el = li.select_one(".list__value")
                        time_el = li.find("time")
                        if label_el and time_el:
                            label = label_el.get_text(strip=True)
                            datetime_val = time_el.get("datetime", "")[:10]
                            if "öppnar" in label.lower():
                                dates["registration_opens"] = datetime_val
                            elif "stänger" in label.lower():
                                dates["registration_closes"] = datetime_val
                            elif "återbud" in label.lower():
                                dates["cancellation_deadline"] = datetime_val
                            elif "start" in label.lower():
                                dates["competition_start"] = datetime_val
                            elif "slut" in label.lower():
                                dates["competition_end"] = datetime_val
                
                # Extract event categories
                categories = {
                    "singles_levels": [],
                    "doubles_levels": [],
                    "mixed_levels": [],
                    "doubles_partner": [],
                    "mixed_partner": []
                }
                tid_match = re.search(r'/tournament/([^/]+)', t["url"])
                if tid_match:
                    tid = tid_match.group(1)
                    try:
                        events_resp = ts.get(f"https://badmintonsweden.tournamentsoftware.com/sport/events.aspx?id={tid}", timeout=10)
                        events_soup = BeautifulSoup(events_resp.text, "html.parser")
                        
                        all_events = set()
                        for a in events_soup.select("a"):
                            text = a.get_text(strip=True)
                            if text and len(text) < 50:
                                for cat in ["HS", "DS", "HD", "DD", "MD", "PS", "FS", "PD", "FD"]:
                                    if cat in text:
                                        all_events.add(text.strip())
                                        break
                        
                        for event in sorted(all_events):
                            if event.startswith(("HS", "DS")):
                                categories["singles_levels"].append(event)
                            elif event.startswith(("HD", "DD")):
                                categories["doubles_levels"].append(event)
                            elif event.startswith("MD"):
                                categories["mixed_levels"].append(event)
                        
                        if categories["doubles_levels"]:
                            categories["doubles_partner"] = ["Partner A", "Partner B", "Partner C"]
                        if categories["mixed_levels"]:
                            categories["mixed_partner"] = ["Partner A", "Partner B", "Partner C"]
                    except Exception:
                        pass
                
                return {"tournament": t, "dates": dates, "categories": categories, "success": True}
            except Exception as e:
                logger.debug(f"⚠️  Error fetching {t.get('name', 'Unknown')}: {e}")
                return {"tournament": t, "dates": {}, "categories": {}, "success": False}
        
        # Fetch all tournament details in parallel (5 threads)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_tournament_details, t): t for t in tournaments}
            for future in as_completed(futures):
                results.append(future.result())
        
        logger.info(f"✅ Fetched details for {len(results)} tournaments")
        
        # Write results to DB sequentially (SQLite is single-writer)
        for result in results:
            if not result["success"]:
                continue
            t = result["tournament"]
            dates = result["dates"]
            categories = result["categories"]
            
            try:
                conn = sqlite3.connect(TOURNAMENTS_DB)
                cur = conn.cursor()
                cur.execute("SELECT tournament_name FROM tournaments WHERE tournament_name = ?", (t["name"],))
                existing = cur.fetchone()
                
                if existing:
                    # Tournament exists - update all fields EXCEPT selected_for_view
                    cur.execute("""
                        UPDATE tournaments 
                        SET tournament_url = ?, location = ?, date_start = ?, date_end = ?,
                            registration_opens = ?, registration_closes = ?, cancellation_deadline = ?,
                            competition_start = ?, competition_end = ?, categories = ?, last_updated = CURRENT_TIMESTAMP
                        WHERE tournament_name = ?
                    """, (
                        t["url"], t["location"], t["date_start"], t["date_end"],
                        dates.get("registration_opens", ""), dates.get("registration_closes", ""),
                        dates.get("cancellation_deadline", ""), dates.get("competition_start", ""),
                        dates.get("competition_end", ""), json.dumps(categories), t["name"]
                    ))
                    updated_count += 1
                else:
                    # New tournament - insert with selected_for_view = 0
                    cur.execute("""
                        INSERT INTO tournaments 
                        (tournament_url, tournament_name, location, date_start, date_end,
                         registration_opens, registration_closes, cancellation_deadline,
                         competition_start, competition_end, categories, selected_for_view, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                    """, (
                        t["url"], t["name"], t["location"], t["date_start"], t["date_end"],
                        dates.get("registration_opens", ""), dates.get("registration_closes", ""),
                        dates.get("cancellation_deadline", ""), dates.get("competition_start", ""),
                        dates.get("competition_end", ""), json.dumps(categories)
                    ))
                    logger.info(f"✅ Added new tournament: {t['name']}")
                    added_count += 1
                
                conn.commit()
                conn.close()
                
            except Exception as e:
                logger.error(f"❌ Error processing tournament {t.get('name', 'Unknown')}: {e}")
        
        logger.info(f"📊 Summary: Added {added_count}, Updated {updated_count} tournaments")
        
        # STEP 3: Delete expired tournaments (where date_start < today - can't register after start)
        from datetime import datetime as dt
        today = dt.now().strftime("%Y-%m-%d")
        try:
            conn = sqlite3.connect(TOURNAMENTS_DB)
            cur = conn.cursor()
            # Get tournament names that are expired (for cleaning registrations)
            cur.execute("SELECT tournament_name FROM tournaments WHERE date_start < ?", (today,))
            expired_names = [row[0] for row in cur.fetchall()]
            
            if expired_names:
                # Delete registrations for expired tournaments
                placeholders = ','.join(['?' for _ in expired_names])
                cur.execute(f"DELETE FROM tournament_registrations WHERE tournament_name IN ({placeholders})", expired_names)
                reg_deleted = cur.rowcount
                # Delete the tournaments themselves
                cur.execute(f"DELETE FROM tournaments WHERE tournament_name IN ({placeholders})", expired_names)
                deleted_count = cur.rowcount
                conn.commit()
                logger.info(f"🗑️  Deleted {deleted_count} expired tournaments and {reg_deleted} registrations")
            conn.close()
        except Exception as e:
            logger.error(f"Error deleting expired tournaments: {e}")
        
        # STEP 4: Get updated selection status
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        try:
            cur.execute("SELECT tournament_url, selected_for_view, admin_reg_end_date, registration_closes, tournament_groups FROM tournaments")
        except Exception:
            cur.execute("SELECT tournament_url, selected_for_view, registration_closes FROM tournaments")
        selection_map_updated = {}
        reg_date_map = {}
        reg_closes_map = {}
        groups_map = {}
        for row in cur.fetchall():
            selection_map_updated[row[0]] = row[1]
            if len(row) > 4:
                reg_date_map[row[0]] = row[2] or ""
                reg_closes_map[row[0]] = row[3] or ""
                try:
                    groups_map[row[0]] = json.loads(row[4]) if row[4] else []
                except Exception:
                    groups_map[row[0]] = []
            elif len(row) > 3:
                reg_date_map[row[0]] = row[2] or ""
                reg_closes_map[row[0]] = row[3] or ""
            else:
                reg_date_map[row[0]] = ""
                reg_closes_map[row[0]] = row[2] or ""
        conn.close()

        # Add selected_for_view, admin_reg_end_date, registration_closes, and tournament_groups
        for t in tournaments:
            t["selected_for_view"] = selection_map_updated.get(t["url"], 0)
            t["admin_reg_end_date"] = reg_date_map.get(t["url"], "")
            t["tournament_groups"] = groups_map.get(t["url"], [])
            if not t.get("registration_closes"):
                t["registration_closes"] = reg_closes_map.get(t["url"], "")

        trigger_sync()
        logger.info(f"✅ get_all_bwf_tournaments completed successfully")
        return jsonify(success=True, tournaments=tournaments)
    except Exception as e:
        logger.error(f"Error in get_all_bwf_tournaments: {str(e)}", exc_info=True)
        return jsonify(success=False, error=str(e), tournaments=[]), 500


# --- Tournament info ---
@app.route("/api/reminder-opt-out", methods=["GET"])
def get_reminder_opt_outs():
    """Get list of tournaments the logged-in player has opted out of reminders"""
    license_id = session.get("bwf_license_id")
    if not license_id:
        return jsonify(success=True, opted_out=[])
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        cur.execute("SELECT tournament_name FROM reminder_opt_out WHERE license_id = ?", (license_id,))
        opted_out = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(success=True, opted_out=opted_out)
    except Exception:
        return jsonify(success=True, opted_out=[])


@app.route("/api/reminder-opt-out", methods=["POST"])
def toggle_reminder_opt_out():
    """Toggle reminder opt-out for a tournament"""
    license_id = session.get("bwf_license_id")
    if not license_id:
        return jsonify(success=False, error="Not logged in")
    
    data = request.json
    tournament_name = data.get("tournament_name", "").strip()
    if not tournament_name:
        return jsonify(success=False, error="Tournament name required")
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Check if already opted out
        cur.execute("SELECT id FROM reminder_opt_out WHERE license_id = ? AND tournament_name = ?",
                   (license_id, tournament_name))
        existing = cur.fetchone()
        
        if existing:
            # Remove opt-out (re-enable reminders)
            conn.execute("DELETE FROM reminder_opt_out WHERE license_id = ? AND tournament_name = ?",
                        (license_id, tournament_name))
            conn.commit()
            conn.close()
            return jsonify(success=True, opted_out=False)
        else:
            # Add opt-out (disable reminders)
            conn.execute("INSERT INTO reminder_opt_out (license_id, tournament_name) VALUES (?, ?)",
                        (license_id, tournament_name))
            conn.commit()
            conn.close()
            return jsonify(success=True, opted_out=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/open-tournaments", methods=["GET"])
def open_tournaments():
    """Fetch tournaments selected for view AND not expired, filtered by player's groups"""
    try:
        from datetime import datetime as dt
        today = dt.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Get tournaments marked as selected_for_view = 1 AND date_start >= TODAY
        cur.execute("""
            SELECT tournament_url, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end, admin_reg_end_date, tournament_groups
            FROM tournaments 
            WHERE selected_for_view = 1 
            AND date_start >= ?
            ORDER BY registration_closes ASC, tournament_name ASC
        """, (today,))
        rows = cur.fetchall()
        conn.close()
        
        # Get current player's groups (if logged in and not admin)
        player_groups = None
        license_id = session.get("bwf_license_id")
        is_admin = session.get("admin", False)
        
        if license_id and not is_admin:
            try:
                conn_p = sqlite3.connect(PLAYERS_DB)
                cur_p = conn_p.cursor()
                cur_p.execute("SELECT groups FROM kometPlayers WHERE license_id = ?", (license_id,))
                row_p = cur_p.fetchone()
                conn_p.close()
                if row_p and row_p[0]:
                    player_groups = json.loads(row_p[0])
            except Exception:
                player_groups = None
        
        tournaments = []
        for row in rows:
            tournament_groups_json = row[11]
            tournament_groups = []
            if tournament_groups_json:
                try:
                    tournament_groups = json.loads(tournament_groups_json)
                except Exception:
                    pass
            
            # Filter: if player has groups, only show tournaments that match OR have no groups/have "all"
            if player_groups is not None and not is_admin:
                if tournament_groups:
                    # Tournament has groups assigned - check if player's groups overlap
                    # "All" in tournament_groups means show to everyone
                    if "All" not in tournament_groups and "all" not in tournament_groups and not set(player_groups).intersection(set(tournament_groups)):
                        continue  # Player's groups don't match this tournament
                # If tournament has no groups assigned, show to everyone
            
            tournaments.append({
                "url": row[0],
                "name": row[1],
                "location": row[2],
                "date_start": row[3],
                "date_end": row[4],
                "registration_opens": row[5],
                "registration_closes": row[6],
                "cancellation_deadline": row[7],
                "competition_start": row[8],
                "competition_end": row[9],
                "admin_reg_end_date": row[10] or ""
            })
        
        return jsonify(tournaments=tournaments)
    except Exception as e:
        logger.error(f"Error fetching open tournaments from database: {str(e)}")
        return jsonify(tournaments=[])


@app.route("/api/my-registrations", methods=["GET"])
def my_registrations():
    """Check which tournaments the logged-in player is registered in."""
    license_id = session.get("bwf_license_id")
    if not license_id:
        return jsonify(success=False, registered_urls=[])
    
    logger.info(f"📋 Checking registrations for license_id: {license_id}")
    
    try:
        # Get all tournaments
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT tournament_name, tournament_url
            FROM tournaments
        """)
        
        registered_urls = []
        for tournament_name, tournament_url in cur.fetchall():
            # Check if player is registered in this tournament
            cur.execute("""
                SELECT id FROM tournament_registrations 
                WHERE tournament_name=? AND license_id=?
            """, (tournament_name, license_id))
            
            if cur.fetchone():
                registered_urls.append(tournament_url)
                logger.debug(f"✅ Player registered for: {tournament_name}")
        
        conn.close()
        logger.info(f"✅ Found {len(registered_urls)} registrations for player")
        return jsonify(success=True, registered_urls=registered_urls)
    
    except Exception as e:
        logger.error(f"❌ Error fetching registrations: {str(e)}")
        return jsonify(success=True, registered_urls=[])


@app.route("/api/tournament-registration-counts", methods=["GET"])
def tournament_registration_counts():
    """Get registration counts per tournament (for admin homepage view)"""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT t.tournament_url, COUNT(tr.id) as reg_count
            FROM tournaments t
            LEFT JOIN tournament_registrations tr ON t.tournament_name = tr.tournament_name
            WHERE t.selected_for_view = 1
            GROUP BY t.tournament_url
        """)
        
        counts = {}
        for row in cur.fetchall():
            counts[row[0]] = row[1]
        
        conn.close()
        return jsonify(success=True, counts=counts)
    except Exception as e:
        logger.error(f"❌ Error fetching registration counts: {e}")
        return jsonify(success=True, counts={})


@app.route("/api/ensure-tournament", methods=["POST"])
def ensure_tournament():
    """Ensure tournament exists in unified tournaments.db and creates individual tournament DB"""
    data = request.json
    url = data.get("url", "")
    if not url:
        return jsonify(success=False, error="URL required"), 400

    logger.info(f"📋 Ensuring tournament exists for URL: {url}")
    
    try:
        # Check if tournament already exists in unified schema
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT tournament_name FROM tournaments WHERE tournament_url=?
        """, (url,))
        
        result = cur.fetchone()
        if result:
            tournament_name = result[0]
            conn.close()
            logger.info(f"✅ Tournament already exists with name: {tournament_name}")
            return jsonify(success=True, tournament_id=tournament_name, db=tournament_name, created=False)
        
        conn.close()
        
        # Fetch tournament info from BWF
        logger.info(f"🔍 Fetching tournament info from Badminton Sweden...")
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        resp = s.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        name = ""
        name_el = soup.select_one(".media__title a")
        if name_el:
            name = name_el.get_text(strip=True)
        if not name:
            name_el = soup.select_one(".media__title")
            if name_el:
                name = name_el.get_text(strip=True)

        # Get location
        location = ""
        location_el = soup.select_one(".media__subheading")
        if location_el:
            location = location_el.get_text(strip=True)

        # Get timeline dates
        dates = {}
        timeline = soup.select_one(".tournament-meta__timeline")
        if timeline:
            for li in timeline.find_all("li"):
                label_el = li.select_one(".list__value")
                time_el = li.find("time")
                if label_el and time_el:
                    label = label_el.get_text(strip=True)
                    datetime_val = time_el.get("datetime", "")[:10]
                    if "\u00f6ppnar" in label.lower():
                        dates["registration_opens"] = datetime_val
                    elif "st\u00e4nger" in label.lower():
                        dates["registration_closes"] = datetime_val
                    elif "\u00e5terbud" in label.lower():
                        dates["cancellation_deadline"] = datetime_val
                    elif "start" in label.lower():
                        dates["competition_start"] = datetime_val
                    elif "slut" in label.lower():
                        dates["competition_end"] = datetime_val

        # Extract event categories/levels mapped to registration fields
        categories = {
            "singles_levels": [],
            "doubles_levels": [],
            "mixed_levels": [],
            "doubles_partner": [],
            "mixed_partner": []
        }
        import re
        tid_match = re.search(r'/tournament/([^/]+)', url)
        if tid_match:
            tid = tid_match.group(1)
            try:
                events_resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/sport/events.aspx?id={tid}", timeout=10)
                events_soup = BeautifulSoup(events_resp.text, "html.parser")
                
                # Extract event categories and map to registration fields
                all_events = set()
                for a in events_soup.select("a"):
                    text = a.get_text(strip=True)
                    if text and len(text) < 50:
                        # Check for category codes
                        for cat in ["HS", "DS", "HD", "DD", "MD", "PS", "FS", "PD", "FD"]:
                            if cat in text:
                                all_events.add(text.strip())
                                break
                
                # Map events to registration fields
                for event in sorted(all_events):
                    if event.startswith(("HS", "DS")):
                        categories["singles_levels"].append(event)
                    elif event.startswith(("HD", "DD")):
                        categories["doubles_levels"].append(event)
                    elif event.startswith("MD"):
                        categories["mixed_levels"].append(event)
                
                # Set partner options (typical pattern)
                if categories["doubles_levels"]:
                    categories["doubles_partner"] = ["Partner A", "Partner B", "Partner C"]
                if categories["mixed_levels"]:
                    categories["mixed_partner"] = ["Partner A", "Partner B", "Partner C"]
                
                logger.debug(f"✅ Extracted categories: {categories}")
            except Exception as e:
                logger.debug(f"⚠️  Could not extract categories: {e}")

        if not name:
            return jsonify(success=False, error="Could not fetch tournament info"), 500

        # STEP 1: Add to unified tournaments.db with all date fields
        logger.info(f"📝 Adding tournament to unified tournaments.db...")
        logger.info(f"   Tournament: {name}")
        logger.info(f"   Location: {location}")
        logger.info(f"   Extracted dates: {dates}")
        
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO tournaments
                (tournament_url, tournament_name, location, date_start, date_end,
                 registration_opens, registration_closes, cancellation_deadline,
                 competition_start, competition_end, categories, selected_for_view, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                url,
                name,
                location,
                dates.get("competition_start", ""),  # date_start
                dates.get("competition_end", ""),    # date_end
                dates.get("registration_opens", ""),
                dates.get("registration_closes", ""),
                dates.get("cancellation_deadline", ""),
                dates.get("competition_start", ""),
                dates.get("competition_end", ""),
                json.dumps(categories),
                1  # selected_for_view = true
            ))
            conn.commit()
            
            # Get the name to return
            tournament_name = name
            logger.info(f"✅ Added to tournaments.db with name: {tournament_name}")
            logger.info(f"   Saved dates:")
            logger.info(f"     registration_opens: {dates.get('registration_opens', '')}")
            logger.info(f"     registration_closes: {dates.get('registration_closes', '')}")
            logger.info(f"     cancellation_deadline: {dates.get('cancellation_deadline', '')}")
            logger.info(f"     competition_start: {dates.get('competition_start', '')}")
            logger.info(f"     competition_end: {dates.get('competition_end', '')}")
        except Exception as e:
            logger.warning(f"⚠️  Could not add to unified DB: {e}")
            logger.exception("Full traceback:")
            tournament_name = None
        finally:
            conn.close()

        logger.info(f"✅ Tournament successfully added to unified tournaments.db")
        trigger_sync()  # Trigger debounced sync after tournament creation
        
        return jsonify(success=True, tournament_id=tournament_name, db=tournament_name, created=True)
    except Exception as e:
        logger.error(f"❌ Error in ensure_tournament: {e}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/tournament-events", methods=["GET"])
def get_tournament_events():
    """Fetch event classes from tournament database (cached during import)."""
    db_file = request.args.get("dbFile")
    if not db_file:
        return jsonify(success=False, error="dbFile required"), 400
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    try:
        # Get categories for the specific tournament
        cur.execute("SELECT categories FROM tournaments WHERE tournament_name = ?", (db_file,))
        row = cur.fetchone()
        
        if row and row[0]:
            categories = json.loads(row[0])
            logger.debug(f"✅ Using cached categories for {db_file}: {categories}")
            
            # Return structured category data for registration form
            conn.close()
            return jsonify(success=True, categories=categories)
    except Exception as e:
        logger.debug(f"Could not read categories from DB: {e}")
    
    conn.close()
    
    # Fallback: Return empty structured response
    logger.warning(f"⚠️  No categories found for tournament: {db_file}")
    return jsonify(success=True, categories={
        "singles_levels": [],
        "doubles_levels": [],
        "mixed_levels": [],
        "doubles_partner": [],
        "mixed_partner": []
    })


@app.route("/api/tournament", methods=["GET"])
def get_tournament_info():
    """Get tournament info including categories from tournaments.db"""
    tournament_name = request.args.get("dbFile")  # This is the tournament name from tournaments.db
    
    if not tournament_name:
        return jsonify(success=False, error="dbFile required"), 400
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT tournament_name, registration_closes, cancellation_deadline, categories, admin_reg_end_date, tournament_groups
            FROM tournaments WHERE tournament_name = ?
        """, (tournament_name,))
        
        row = cur.fetchone()
        
        if not row:
            # Tournament not found in tournaments table
            # Return minimal info from registrations if they exist
            cur.execute(
                "SELECT COUNT(*) FROM tournament_registrations WHERE tournament_name = ?",
                (tournament_name,)
            )
            if cur.fetchone()[0] > 0:
                # Registrations exist, return basic info
                conn.close()
                return jsonify(success=True, tournament={
                    "name": f"Tournament {tournament_name}",
                    "registration_closes": "",
                    "admin_reg_end_date": "",
                    "cancellation_deadline": "",
                    "categories": {},
                    "tournament_groups": [],
                    "eligible_players": []
                })
            else:
                conn.close()
                return jsonify(success=False, error="Tournament not found"), 404
        
        tournament_name_val, registration_closes, cancellation_deadline, categories_json, admin_reg_end_date, tournament_groups_json = row
        categories = json.loads(categories_json) if categories_json else {}
        tournament_groups = []
        try:
            tournament_groups = json.loads(tournament_groups_json) if tournament_groups_json else []
        except Exception:
            pass
        
        conn.close()
        
        # Get eligible players from kometPlayers based on tournament groups
        eligible_players = []
        if session.get("admin"):
            try:
                conn_p = sqlite3.connect(PLAYERS_DB)
                cur_p = conn_p.cursor()
                
                if tournament_groups:
                    # Get players whose groups overlap with tournament groups
                    cur_p.execute("SELECT name, license_id, email, groups FROM kometPlayers ORDER BY name")
                    for p_row in cur_p.fetchall():
                        player_groups = []
                        try:
                            player_groups = json.loads(p_row[3]) if p_row[3] else []
                        except Exception:
                            pass
                        # Player is eligible if: "All" in tournament_groups, or player's groups overlap
                        if "All" in tournament_groups or set(player_groups).intersection(set(tournament_groups)):
                            eligible_players.append({"name": p_row[0], "license_id": p_row[1], "email": p_row[2] or ""})
                else:
                    # No groups assigned - all komet players are eligible
                    cur_p.execute("SELECT name, license_id, email FROM kometPlayers ORDER BY name")
                    eligible_players = [{"name": r[0], "license_id": r[1], "email": r[2] or ""} for r in cur_p.fetchall()]
                
                conn_p.close()
            except Exception as e:
                logger.debug(f"Could not fetch eligible players: {e}")
        
        return jsonify(success=True, tournament={
            "name": tournament_name_val,
            "registration_closes": registration_closes or "",
            "admin_reg_end_date": admin_reg_end_date or "",
            "cancellation_deadline": cancellation_deadline or "",
            "categories": categories,
            "tournament_groups": tournament_groups,
            "eligible_players": eligible_players
        })
    
    except Exception as e:
        logger.error(f"❌ Error fetching tournament info: {e}")
        return jsonify(success=False, error=str(e)), 500


# --- Players in tournament ---
@app.route("/api/tournament-players", methods=["GET"])
def get_tournament_players():
    """Get registered players for a tournament"""
    tournament_name = request.args.get("dbFile")  # This is the tournament name from tournaments.db
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", 20))
    
    if not tournament_name:
        return jsonify(success=False, error="dbFile required"), 400
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get total registered players
        cur.execute(
            "SELECT COUNT(*) FROM tournament_registrations WHERE tournament_name = ?",
            (tournament_name,)
        )
        total = cur.fetchone()[0]
        
        # Get paginated registered players with player details from players.db
        offset = (page - 1) * page_size
        cur.execute("""
            SELECT tr.id as player_id, tr.tournament_name, tr.license_id, 
                   COALESCE(p.name, 'Unknown') as player_name,
                   COALESCE(p.club, '') as club,
                   COALESCE(p.gender, '') as gender,
                   COALESCE(p.email, '') as email,
                   COALESCE(p.phone, '') as phone,
                   tr.singles_levels, tr.doubles_levels, 
                   tr.mixed_levels, tr.doubles_partner, tr.mixed_partner, tr.registration_date
            FROM tournament_registrations tr
            LEFT JOIN players_db.players p ON tr.license_id = p.license_id
            WHERE tr.tournament_name = ? 
            LIMIT ? OFFSET ?
        """, (tournament_name, page_size, offset))
        
        players = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        return jsonify(success=True, total=total, players=players)
    
    except Exception as e:
        logger.error(f"❌ Error fetching tournament players: {e}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/tournament-registrations", methods=["GET"])
def get_tournament_registration():
    """Get a specific player's registration for a tournament"""
    tournament_name = request.args.get("dbFile")
    license_id = request.args.get("license_id")
    
    if not tournament_name or not license_id:
        return jsonify(success=False, error="dbFile and license_id required"), 400
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Verify tournament exists
        cur.execute("SELECT tournament_name FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        if not cur.fetchone():
            conn.close()
            return jsonify(success=False, error="Tournament not found"), 404
        
        # Get player's registration
        cur.execute("""
            SELECT id, tournament_name, license_id, singles_levels, doubles_levels, 
                   mixed_levels, doubles_partner, mixed_partner, registration_date
            FROM tournament_registrations 
            WHERE tournament_name = ? AND license_id = ?
        """, (tournament_name, license_id))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            # No existing registration
            return jsonify(success=True, registration=None)
        
        registration = {
            "player_id": row[0],
            "tournament_name": row[1],
            "license_id": row[2],
            "singles_levels": row[3] or "",
            "doubles_levels": row[4] or "",
            "mixed_levels": row[5] or "",
            "doubles_partner": row[6] or "",
            "mixed_partner": row[7] or "",
            "registration_date": row[8]
        }
        
        return jsonify(success=True, registration=registration)
    
    except Exception as e:
        logger.error(f"❌ Error fetching tournament registration: {e}")
        return jsonify(success=False, error=str(e)), 500


def _check_points_too_high(license_id, event_class):
    """
    Check if a player's points exceed the maximum for a given event class.
    This is a hard block — registration must be rejected.
    
    Args:
        license_id: Player's license ID
        event_class: e.g. "DD A", "HD B", "MD Elit"
    
    Returns:
        (blocked: bool, message: str)
    """
    try:
        parts = event_class.strip().split(" ", 1)
        if len(parts) != 2:
            return False, ""
        category = parts[0]  # HD, DD, MD, HS, DS
        level = parts[1]     # A, B, C, D, Elit
        
        adult_classes = {"Elit", "A", "B", "C", "D"}
        if level not in adult_classes:
            return False, ""
        
        # Get player ranking
        conn_p = sqlite3.connect(PLAYERS_DB)
        cur_p = conn_p.cursor()
        cur_p.execute("SELECT ranking FROM players WHERE license_id = ?", (license_id,))
        row = cur_p.fetchone()
        conn_p.close()
        
        if not row or not row[0]:
            return False, ""
        
        player_ranking = json.loads(row[0])
        # Handle double-encoded JSON
        if isinstance(player_ranking, str):
            player_ranking = json.loads(player_ranking)
        cat_ranking = player_ranking.get(category, {})
        points_str = cat_ranking.get("points", "")
        if not points_str:
            return False, ""
        
        points = int(points_str)
        
        # Get max points rule
        conn_r = sqlite3.connect(POINTS_DB)
        conn_r.row_factory = sqlite3.Row
        cur_r = conn_r.cursor()
        cur_r.execute("SELECT * FROM point_rules WHERE klass=?", (level,))
        rule = cur_r.fetchone()
        conn_r.close()
        
        if not rule:
            return False, ""
        
        col_max = f"{category.lower()}_max"
        max_pts = rule[col_max]
        
        if max_pts is not None and points > max_pts:
            return True, f"{category} points ({points}) exceed maximum ({max_pts}) for {level} class. Not allowed to play {event_class}."
        
        return False, ""
    except Exception as e:
        logger.debug(f"Error in _check_points_too_high: {e}")
        return False, ""


def _check_partner_availability(tournament_name, partner_license_id, partner_name, category_type, requesting_player_name):
    """
    Check if a partner is already registered for the same category with another player.
    
    Args:
        tournament_name: Tournament name
        partner_license_id: Partner's license ID
        partner_name: Partner's name (for error messages)
        category_type: 'doubles' or 'mixed'
        requesting_player_name: Name of the player trying to add this partner
    
    Returns:
        (available: bool, message: str)
    """
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT doubles_levels, mixed_levels, doubles_partner, mixed_partner FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?",
            (tournament_name, partner_license_id)
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            # Partner not registered yet - available
            return True, ""
        
        doubles_levels, mixed_levels, existing_doubles_partner, existing_mixed_partner = row
        
        if category_type == "doubles":
            # Check if partner already has doubles registered with someone else
            if doubles_levels and existing_doubles_partner and existing_doubles_partner != requesting_player_name:
                return False, f"{partner_name} is already playing doubles ({doubles_levels}) with {existing_doubles_partner} in this tournament."
        elif category_type == "mixed":
            # Check if partner already has mixed registered with someone else
            if mixed_levels and existing_mixed_partner and existing_mixed_partner != requesting_player_name:
                return False, f"{partner_name} is already playing mixed ({mixed_levels}) with {existing_mixed_partner} in this tournament."
        
        return True, ""
    
    except Exception as e:
        logger.error(f"⚠️  Error checking partner availability: {e}")
        return True, ""  # Allow if check fails


@app.route("/api/validate-partner", methods=["POST"])
def validate_partner():
    """API endpoint to check if a partner is available for a category in a tournament"""
    data = request.json
    tournament_name = data.get("tournament_name", "")
    partner_license_id = data.get("partner_license_id", "")
    partner_name = data.get("partner_name", "")
    category_type = data.get("category_type", "")  # 'doubles' or 'mixed'
    requesting_player_name = data.get("requesting_player_name", "")
    
    if not tournament_name or not partner_license_id or not category_type:
        return jsonify(success=True, available=True)
    
    available, message = _check_partner_availability(
        tournament_name, partner_license_id, partner_name, category_type, requesting_player_name
    )
    
    return jsonify(success=True, available=available, message=message)


def _cleanup_removed_partner(cur, tournament_name, partner_name, category_type, player_name):
    """
    Clean up a partner's registration when they are removed from a player's category.
    
    When Player A removes Player B as partner in doubles/mixed:
    - Clear Player B's corresponding category and partner reference
    - If Player B has no remaining categories, delete their registration entirely
    
    Works for all partner categories: HD, DD, MD (doubles and mixed).
    
    Args:
        cur: database cursor (already connected to TOURNAMENTS_DB)
        tournament_name: tournament name
        partner_name: name of the partner being removed
        category_type: 'doubles' or 'mixed'
        player_name: name of the player who removed the partner
    """
    try:
        # Find partner's registration by their name as a partner reference
        # The partner's registration has player_name listed as their partner
        if category_type == "doubles":
            cur.execute("""
                UPDATE tournament_registrations
                SET doubles_levels = '', doubles_partner = ''
                WHERE tournament_name = ? AND doubles_partner = ?
            """, (tournament_name, player_name))
            logger.info(f"🔄 Cleared doubles from partner {partner_name} (was paired with {player_name})")
        elif category_type == "mixed":
            cur.execute("""
                UPDATE tournament_registrations
                SET mixed_levels = '', mixed_partner = ''
                WHERE tournament_name = ? AND mixed_partner = ?
            """, (tournament_name, player_name))
            logger.info(f"🔄 Cleared mixed from partner {partner_name} (was paired with {player_name})")
        
        # Remove registrations that now have no remaining categories
        cur.execute("""
            DELETE FROM tournament_registrations
            WHERE tournament_name = ? AND
                (singles_levels IS NULL OR singles_levels = '') AND
                (doubles_levels IS NULL OR doubles_levels = '') AND
                (mixed_levels IS NULL OR mixed_levels = '')
        """, (tournament_name,))
        removed = cur.rowcount
        if removed > 0:
            logger.info(f"🗑️  Removed {removed} registration(s) with no remaining categories")
    except Exception as e:
        logger.error(f"⚠️  Error cleaning up removed partner: {e}")


def _register_partner(tournament_name, partner_license_id, partner_name, partner_club="", partner_profile_url="", doubles_levels="", mixed_levels="", doubles_partner="", mixed_partner=""):
    """
    Register a partner player in both players.db and tournament_registrations.
    Called when admin registers a player with a doubles/mixed partner.
    """
    now = __import__('datetime').datetime.now().isoformat()
    
    # Fetch partner's ranking from public profile
    partner_ranking = None
    if partner_profile_url:
        try:
            s = ext_requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0"})
            s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
                "ReturnUrl": "/",
                "SettingsOpen": "false",
                "CookieWallCategoryPreferences": "1,2,3"
            }, allow_redirects=True, timeout=5)
            ranking_resp = s.get(f"https://badmintonsweden.tournamentsoftware.com{partner_profile_url}/ranking", timeout=10)
            ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
            table = ranking_soup.find("table")
            if table:
                ranking_data = {}
                for row in table.find_all("tr")[1:]:
                    th = row.find("th", scope="row")
                    tds = row.find_all("td")
                    if th and len(tds) >= 2:
                        category = th.get_text(strip=True)
                        if category:
                            ranking_data[category] = {"rank": tds[0].get_text(strip=True), "points": tds[1].get_text(strip=True)}
                if ranking_data:
                    partner_ranking = json.dumps(ranking_data)
                    logger.info(f"✅ Fetched ranking for partner {partner_name}")
        except Exception as e:
            logger.debug(f"Could not fetch partner ranking: {e}")
    
    # Insert/update partner in players.db
    try:
        conn_players = sqlite3.connect(PLAYERS_DB)
        cur_players = conn_players.cursor()
        
        cur_players.execute("SELECT id FROM players WHERE license_id = ?", (partner_license_id,))
        existing = cur_players.fetchone()
        
        if existing:
            # Update existing - preserve login data
            cur_players.execute("""
                UPDATE players SET
                    name = ?,
                    profile_url = COALESCE(?, profile_url),
                    club = COALESCE(?, club),
                    ranking = COALESCE(?, ranking),
                    last_updated = ?
                WHERE license_id = ?
            """, (partner_name, partner_profile_url or None, partner_club or None, partner_ranking, now, partner_license_id))
        else:
            # Insert new partner player
            cur_players.execute("""
                INSERT INTO players (license_id, name, profile_url, club, ranking, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (partner_license_id, partner_name, partner_profile_url, partner_club, partner_ranking, now))
        
        conn_players.commit()
        conn_players.close()
        logger.info(f"✅ Partner {partner_name} ({partner_license_id}) saved to players.db")
    except Exception as e:
        logger.error(f"⚠️  Error saving partner to players.db: {e}")
    
    # Insert/update partner registration in tournament_registrations
    try:
        conn_tour = sqlite3.connect(TOURNAMENTS_DB)
        cur_tour = conn_tour.cursor()
        
        cur_tour.execute(
            "SELECT id FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?",
            (tournament_name, partner_license_id)
        )
        existing_reg = cur_tour.fetchone()
        
        if existing_reg:
            # Update existing registration - add the partner category
            if doubles_levels:
                cur_tour.execute("""
                    UPDATE tournament_registrations
                    SET doubles_levels = COALESCE(?, doubles_levels),
                        doubles_partner = ?,
                        registration_date = CURRENT_TIMESTAMP
                    WHERE tournament_name = ? AND license_id = ?
                """, (doubles_levels, doubles_partner, tournament_name, partner_license_id))
            if mixed_levels:
                cur_tour.execute("""
                    UPDATE tournament_registrations
                    SET mixed_levels = COALESCE(?, mixed_levels),
                        mixed_partner = ?,
                        registration_date = CURRENT_TIMESTAMP
                    WHERE tournament_name = ? AND license_id = ?
                """, (mixed_levels, mixed_partner, tournament_name, partner_license_id))
        else:
            # Insert new registration for partner
            cur_tour.execute("""
                INSERT INTO tournament_registrations 
                (tournament_name, license_id, singles_levels, doubles_levels, mixed_levels,
                 doubles_partner, mixed_partner, registration_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                tournament_name,
                partner_license_id,
                "",  # Partner might not play singles
                doubles_levels,
                mixed_levels,
                doubles_partner,
                mixed_partner
            ))
        
        conn_tour.commit()
        conn_tour.close()
        logger.info(f"✅ Partner {partner_name} registered for tournament {tournament_name}")
    except Exception as e:
        logger.error(f"⚠️  Error registering partner for tournament: {e}")


@app.route("/api/add-player", methods=["POST"])
def add_player():
    """Register a player for a tournament"""
    data = request.json
    tournament_name = data.get("dbFile")  # This is the tournament name from tournaments.db
    player = data.get("player")
    
    if not tournament_name or not player:
        return jsonify(success=False, error="Missing data"), 400
    
    license_id = player.get("license_id", "").strip()
    
    if not license_id:
        return jsonify(success=False, error="license_id required"), 400
    
    # SERVER-SIDE VALIDATION: Reject if player's points exceed max for any selected category
    # This is a hard block — cannot be overridden
    try:
        conn_players_check = sqlite3.connect(PLAYERS_DB)
        cur_check = conn_players_check.cursor()
        cur_check.execute("SELECT ranking FROM players WHERE license_id = ?", (license_id,))
        row = cur_check.fetchone()
        player_ranking = {}
        if row and row[0]:
            decoded = json.loads(row[0])
            # Handle double-encoded JSON (string inside string)
            if isinstance(decoded, str):
                decoded = json.loads(decoded)
            if isinstance(decoded, dict):
                player_ranking = decoded
        conn_players_check.close()
        
        if player_ranking:
            conn_rules = sqlite3.connect(POINTS_DB)
            conn_rules.row_factory = sqlite3.Row
            cur_rules = conn_rules.cursor()
            
            all_levels = []
            for lvl_str in [player.get("singles_levels", ""), player.get("doubles_levels", ""), player.get("mixed_levels", "")]:
                if lvl_str:
                    for lvl in lvl_str.split(","):
                        lvl = lvl.strip()
                        if lvl:
                            parts = lvl.split(" ", 1)
                            if len(parts) == 2:
                                all_levels.append({"event": lvl, "category": parts[0], "level": parts[1]})
            
            for entry in all_levels:
                category = entry["category"]
                level = entry["level"]
                adult_classes = {"Elit", "A", "B", "C", "D"}
                if level not in adult_classes:
                    continue
                
                cur_rules.execute("SELECT * FROM point_rules WHERE klass=?", (level,))
                rule = cur_rules.fetchone()
                if not rule:
                    continue
                
                col_max = f"{category.lower()}_max"
                max_pts = rule[col_max]
                
                cat_ranking = player_ranking.get(category, {})
                points_str = cat_ranking.get("points", "")
                if points_str and max_pts is not None:
                    try:
                        points = int(points_str)
                        if points > max_pts:
                            conn_rules.close()
                            return jsonify(success=False, 
                                error=f"Registration rejected: {category} points ({points}) exceed maximum ({max_pts}) for {level} class. Not allowed to play {entry['event']}.")
                    except ValueError:
                        pass
            
            conn_rules.close()
    except Exception as e:
        logger.debug(f"Could not validate points on server: {e}")
    
    # SERVER-SIDE VALIDATION: Reject if player is too old for age-based category (U9, U11, etc.)
    # This is a hard block — cannot be overridden
    try:
        conn_players_age = sqlite3.connect(PLAYERS_DB)
        cur_age = conn_players_age.cursor()
        cur_age.execute("SELECT dob FROM players WHERE license_id = ?", (license_id,))
        row_age = cur_age.fetchone()
        player_dob = row_age[0] if row_age and row_age[0] else ""
        conn_players_age.close()
        
        if player_dob:
            from datetime import datetime as dt_cls
            import re as re_mod
            birth = dt_cls.strptime(player_dob, "%Y-%m-%d")
            
            # Get competition date for this tournament
            conn_t = sqlite3.connect(TOURNAMENTS_DB)
            cur_t = conn_t.cursor()
            cur_t.execute("SELECT competition_start FROM tournaments WHERE tournament_name = ?", (tournament_name,))
            t_row = cur_t.fetchone()
            competition_date = t_row[0] if t_row else ""
            conn_t.close()
            
            check_date = dt_cls.now()
            if competition_date:
                try:
                    check_date = dt_cls.strptime(competition_date, "%Y-%m-%d")
                except Exception:
                    pass
            
            age_at_comp = check_date.year - birth.year - ((check_date.month, check_date.day) < (birth.month, birth.day))
            
            all_levels = []
            for lvl_str in [player.get("singles_levels", ""), player.get("doubles_levels", ""), player.get("mixed_levels", "")]:
                if lvl_str:
                    for lvl in lvl_str.split(","):
                        lvl = lvl.strip()
                        if lvl:
                            parts = lvl.split(" ", 1)
                            if len(parts) == 2:
                                all_levels.append({"event": lvl, "category": parts[0], "level": parts[1]})
            
            for entry in all_levels:
                level = entry["level"]
                # HARD BLOCK: Under 18 cannot play C or D class (seniors only)
                if level in {"C", "D"} and age_at_comp < 18:
                    return jsonify(success=False,
                        error=f"Registration rejected: Player is {age_at_comp} years old. {level} class is for seniors (18+) only. Juniors can only play B, A, or Elit.")
                
                # Check age-based categories (U9, U11, U13, U15, U17, U19)
                if level.startswith("U"):
                    match = re_mod.search(r'\d+', level)
                    if match:
                        age_limit = int(match.group())
                        year_turn_limit = birth.year + age_limit
                        
                        if age_at_comp >= age_limit:
                            # Grace period: can play until June of the year they age out
                            if check_date.year == year_turn_limit and check_date.month <= 6:
                                pass  # Allowed
                            else:
                                return jsonify(success=False,
                                    error=f"Registration rejected: Player is {age_at_comp} years old. {level} is for players under {age_limit}. Not allowed to play {entry['event']}.")
    except Exception as e:
        logger.debug(f"Could not validate age on server: {e}")
    
    # STEP 1: Ensure player exists in players.db
    # From live search we have: name, license_id, club, profile_url
    # From player profile we have: gender, ranking
    # We do NOT have: email, phone, dob, age (only available on login)
    try:
        conn_players = sqlite3.connect(PLAYERS_DB)
        cur_players = conn_players.cursor()
        
        # Check if player already exists
        cur_players.execute("SELECT id FROM players WHERE license_id = ?", (license_id,))
        existing_player = cur_players.fetchone()
        
        now = __import__('datetime').datetime.now().isoformat()
        ranking_json = json.dumps(player.get("ranking")) if player.get("ranking") else None
        
        if existing_player:
            # Update existing player - only overwrite fields we have reliable data for
            # Preserve email, phone, dob, age (only comes from login)
            cur_players.execute("""
                UPDATE players SET
                    name = ?,
                    profile_url = COALESCE(?, profile_url),
                    club = ?,
                    gender = COALESCE(?, gender),
                    ranking = COALESCE(?, ranking),
                    last_updated = ?
                WHERE license_id = ?
            """, (
                player.get("player_name", ""),
                player.get("profile_url") or None,
                player.get("club", ""),
                player.get("gender") or None,
                ranking_json,
                now,
                license_id
            ))
            logger.info(f"✅ Updated player {player.get('player_name')} in players.db")
        else:
            # Insert new player with fields available from live search + profile
            cur_players.execute("""
                INSERT INTO players (license_id, name, profile_url, club, gender, ranking, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                license_id,
                player.get("player_name", ""),
                player.get("profile_url", ""),
                player.get("club", ""),
                player.get("gender", ""),
                ranking_json,
                now
            ))
            logger.info(f"✅ Inserted player {player.get('player_name')} into players.db")
        
        conn_players.commit()
        conn_players.close()
    except Exception as e:
        logger.error(f"⚠️  Error saving player to players.db: {e}")
    
    # STEP 2: Register player in tournament_registrations
    try:
        conn_main = sqlite3.connect(TOURNAMENTS_DB)
        cur_main = conn_main.cursor()
        
        cur_main.execute("SELECT tournament_name FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        if not cur_main.fetchone():
            conn_main.close()
            return jsonify(success=False, error="Tournament not found"), 404
        
        # Check if this player is already registered for this tournament
        cur_main.execute(
            "SELECT id FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?",
            (tournament_name, license_id)
        )
        existing_registration = cur_main.fetchone()
        
        if existing_registration:
            # Get current registration to detect removed partners
            cur_main.execute("""
                SELECT doubles_partner, mixed_partner, doubles_levels, mixed_levels
                FROM tournament_registrations WHERE tournament_name = ? AND license_id = ?
            """, (tournament_name, license_id))
            old_reg = cur_main.fetchone()
            old_doubles_partner = old_reg[0] if old_reg else ""
            old_mixed_partner = old_reg[1] if old_reg else ""
            old_doubles_levels = old_reg[2] if old_reg else ""
            old_mixed_levels = old_reg[3] if old_reg else ""
            
            new_doubles_partner = player.get("doubles_partner", "")
            new_mixed_partner = player.get("mixed_partner", "")
            new_doubles_levels = player.get("doubles_levels", "")
            new_mixed_levels = player.get("mixed_levels", "")
            player_name_for_cleanup = player.get("player_name", "")

            # Update existing registration
            cur_main.execute("""
                UPDATE tournament_registrations
                SET singles_levels = ?, doubles_levels = ?, mixed_levels = ?,
                    doubles_partner = ?, mixed_partner = ?, registration_date = CURRENT_TIMESTAMP
                WHERE tournament_name = ? AND license_id = ?
            """, (
                player.get("singles_levels", ""),
                new_doubles_levels,
                new_mixed_levels,
                new_doubles_partner,
                new_mixed_partner,
                tournament_name,
                license_id
            ))
            logger.info(f"✅ Updated registration for {player.get('player_name')} in tournament {tournament_name}")
            
            # Clean up removed partners
            # If doubles partner was removed, changed, or doubles level was cleared
            doubles_partner_removed = (old_doubles_partner and old_doubles_partner != new_doubles_partner)
            doubles_level_cleared = (old_doubles_levels and not new_doubles_levels and old_doubles_partner)
            if doubles_partner_removed or doubles_level_cleared:
                _cleanup_removed_partner(cur_main, tournament_name, old_doubles_partner, "doubles", player_name_for_cleanup)
            
            # If mixed partner was removed, changed, or mixed level was cleared
            mixed_partner_removed = (old_mixed_partner and old_mixed_partner != new_mixed_partner)
            mixed_level_cleared = (old_mixed_levels and not new_mixed_levels and old_mixed_partner)
            if mixed_partner_removed or mixed_level_cleared:
                _cleanup_removed_partner(cur_main, tournament_name, old_mixed_partner, "mixed", player_name_for_cleanup)
        else:
            # Insert new registration
            cur_main.execute("""
                INSERT INTO tournament_registrations (tournament_name, license_id, singles_levels, doubles_levels, mixed_levels,
                 doubles_partner, mixed_partner, registration_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                tournament_name,
                license_id,
                player.get("singles_levels", ""),
                player.get("doubles_levels", ""),
                player.get("mixed_levels", ""),
                player.get("doubles_partner", ""),
                player.get("mixed_partner", "")
            ))
            logger.info(f"✅ Registered {player.get('player_name')} for tournament {tournament_name}")
        
        conn_main.commit()
        conn_main.close()
        
        # STEP 3: Register partners (doubles/mixed) in players.db and tournament_registrations
        player_name = player.get("player_name", "")
        
        # Register doubles partner
        doubles_partner_name = player.get("doubles_partner", "").strip()
        doubles_partner_license = player.get("doubles_partner_license_id", "").strip()
        doubles_level = player.get("doubles_levels", "")
        if doubles_partner_name and doubles_partner_license and doubles_level:
            # Check partner points too high (hard block)
            blocked, block_msg = _check_points_too_high(doubles_partner_license, doubles_level)
            if blocked:
                return jsonify(success=False, error=f"Partner {doubles_partner_name}: {block_msg}")
            
            # Check if partner is available for doubles
            available, message = _check_partner_availability(
                tournament_name, doubles_partner_license, doubles_partner_name, "doubles", player_name
            )
            if not available:
                return jsonify(success=False, error=message)
            
            _register_partner(
                tournament_name=tournament_name,
                partner_license_id=doubles_partner_license,
                partner_name=doubles_partner_name,
                partner_club=player.get("doubles_partner_club", ""),
                partner_profile_url=player.get("doubles_partner_profile_url", ""),
                doubles_levels=doubles_level,
                doubles_partner=player_name
            )
        
        # Register mixed partner
        mixed_partner_name = player.get("mixed_partner", "").strip()
        mixed_partner_license = player.get("mixed_partner_license_id", "").strip()
        mixed_level = player.get("mixed_levels", "")
        if mixed_partner_name and mixed_partner_license and mixed_level:
            # Check partner points too high (hard block)
            blocked, block_msg = _check_points_too_high(mixed_partner_license, mixed_level)
            if blocked:
                return jsonify(success=False, error=f"Partner {mixed_partner_name}: {block_msg}")
            
            # Check if partner is available for mixed
            available, message = _check_partner_availability(
                tournament_name, mixed_partner_license, mixed_partner_name, "mixed", player_name
            )
            if not available:
                return jsonify(success=False, error=message)
            
            _register_partner(
                tournament_name=tournament_name,
                partner_license_id=mixed_partner_license,
                partner_name=mixed_partner_name,
                partner_club=player.get("mixed_partner_club", ""),
                partner_profile_url=player.get("mixed_partner_profile_url", ""),
                mixed_levels=mixed_level,
                mixed_partner=player_name
            )
        
        trigger_sync()  # Sync after registration
        return jsonify(success=True, message="Registration saved successfully")
    
    except Exception as e:
        logger.error(f"❌ Error registering player: {e}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/delete-player", methods=["POST"])
def delete_player():
    data = request.json
    db_file = data.get("dbFile")  # tournament_name
    player_id = data.get("playerId")  # tournament_registrations.id
    confirm_delete = data.get("confirm", False)
    if not db_file or not player_id:
        return jsonify(success=False, error="Missing data"), 400

    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Get the registration being deleted
        cur.execute("SELECT * FROM tournament_registrations WHERE id = ? AND tournament_name = ?", (player_id, db_file))
        registration = cur.fetchone()
        if not registration:
            conn.close()
            return jsonify(success=False, error="Registration not found"), 404

        license_id = registration["license_id"]
        doubles_partner_name = registration["doubles_partner"] or ""
        mixed_partner_name = registration["mixed_partner"] or ""

        # Check if this player has partners that reference them
        partnerships = []
        auto_remove = []

        # Find others who have this player as their doubles partner
        if doubles_partner_name or mixed_partner_name:
            # Get player name from players.db
            conn_p = sqlite3.connect(PLAYERS_DB)
            cur_p = conn_p.cursor()
            cur_p.execute("SELECT name FROM players WHERE license_id = ?", (license_id,))
            player_row = cur_p.fetchone()
            player_name = player_row[0] if player_row else ""
            conn_p.close()
        else:
            player_name = ""

        if player_name:
            # Find registrations where this player is listed as a partner
            cur.execute("""
                SELECT id, license_id, doubles_partner, mixed_partner, singles_levels, doubles_levels, mixed_levels
                FROM tournament_registrations 
                WHERE tournament_name = ? AND (doubles_partner = ? OR mixed_partner = ?)
            """, (db_file, player_name, player_name))
            
            for p in cur.fetchall():
                if p["doubles_partner"] == player_name:
                    partnerships.append(f"{player_name} is playing doubles with a partner")
                    # If partner has no other categories, they'll be auto-removed
                    if not p["singles_levels"] and not p["mixed_levels"]:
                        auto_remove.append(p["id"])
                if p["mixed_partner"] == player_name:
                    partnerships.append(f"{player_name} is playing mixed with a partner")
                    if not p["singles_levels"] and not p["doubles_levels"]:
                        auto_remove.append(p["id"])

        # If partnerships exist and not confirmed, return warning
        if partnerships and not confirm_delete:
            if auto_remove:
                partnerships.append(f"\nPartners with no remaining categories will also be removed")
            conn.close()
            return jsonify(success=False, needsConfirm=True, warnings=partnerships)

        # Delete the registration
        cur.execute("DELETE FROM tournament_registrations WHERE id = ?", (player_id,))

        # Clear partner references from other registrations
        if player_name:
            cur.execute("""
                UPDATE tournament_registrations 
                SET doubles_partner = '', doubles_levels = '' 
                WHERE tournament_name = ? AND doubles_partner = ?
            """, (db_file, player_name))
            cur.execute("""
                UPDATE tournament_registrations 
                SET mixed_partner = '', mixed_levels = '' 
                WHERE tournament_name = ? AND mixed_partner = ?
            """, (db_file, player_name))

            # Remove registrations that now have no categories left
            cur.execute("""
                DELETE FROM tournament_registrations 
                WHERE tournament_name = ? AND
                    (singles_levels IS NULL OR singles_levels = '') AND
                    (doubles_levels IS NULL OR doubles_levels = '') AND
                    (mixed_levels IS NULL OR mixed_levels = '')
            """, (db_file,))

        conn.commit()
        conn.close()
        trigger_sync()
        return jsonify(success=True)

    except Exception as e:
        logger.error(f"❌ Error deleting player registration: {e}")
        return jsonify(success=False, error=str(e)), 500


# --- Search players live from Badminton Sweden ---
@app.route("/api/search-players", methods=["GET"])
def search_players():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])

    # First check local DB
    conn = sqlite3.connect(PLAYERS_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, name, club, gender FROM players WHERE name LIKE ? LIMIT 20", (f"%{query}%",))
    local_results = [dict(row) for row in cur.fetchall()]

    # Also search live from Badminton Sweden
    try:
        import requests as req
        from bs4 import BeautifulSoup
        resp = req.get(
            "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
            params={"Page": 1, "SportID": 2, "Query": query},
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"},
            timeout=5
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("li.list__item")
        live_results = []
        for item in items:
            name_el = item.select_one("a.media__link span.nav-link__value")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            club = ""
            club_el = item.select_one(".media__subheading span.nav-link__value")
            if club_el:
                club = club_el.get_text(strip=True).split("|")[0].strip()
            license_id = ""
            license_el = item.select_one(".media__title-aside")
            if license_el:
                license_id = license_el.get_text(strip=True).strip("()")
            profile_link = item.select_one("a.media__link")
            profile_url = profile_link.get("href", "") if profile_link else ""
            live_results.append({"name": name, "club": club, "license_id": license_id, "profile_url": profile_url, "source": "live"})
        # Merge: live results first, then local (deduplicated)
        seen = {r["name"] for r in live_results}
        combined = live_results + [r for r in local_results if r["name"] not in seen]
        conn.close()
        return jsonify(combined[:20])
    except Exception:
        conn.close()
        return jsonify(local_results)


@app.route("/api/player-details", methods=["GET"])
def player_details():
    """Fetch full player details (gender, email, phone, ranking) from Badminton Sweden profile."""
    profile_url = request.args.get("profile_url", "").strip()
    player_name = request.args.get("name", "").strip()
    if not profile_url and not player_name:
        return jsonify(success=False, error="profile_url or name required"), 400

    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        # If no profile_url, search for the player
        if not profile_url:
            resp = s.get(
                "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch",
                params={"Page": 1, "SportID": 2, "Query": player_name},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=5
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("li.list__item"):
                name_el = item.select_one("a.media__link span.nav-link__value")
                if name_el and name_el.get_text(strip=True).lower() == player_name.lower():
                    link = item.select_one("a.media__link")
                    if link:
                        profile_url = link.get("href", "")
                    break

        if not profile_url:
            return jsonify(success=False, error="Player profile not found"), 404

        # Fetch player profile page to get gender
        gender = ""
        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com{profile_url}", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        # Gender is often in the profile meta info
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = dt.get_text(strip=True).rstrip(":")
            value = dd.get_text(strip=True)
            if label == "Kön" or "gender" in label.lower():
                gender = "F" if "kvinna" in value.lower() or "female" in value.lower() else "M" if "man" in value.lower() or "male" in value.lower() else ""

        # Try to get email and phone from profile page
        email = ""
        phone = ""
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = dt.get_text(strip=True).rstrip(":")
            value = dd.get_text(strip=True)
            if "e-mail" in label.lower() or "email" in label.lower():
                email = value.replace("(Redigera)", "").strip()
            elif "telefon" in label.lower() or "phone" in label.lower() or "mobil" in label.lower():
                if value and not phone:
                    phone = value

        # If gender not found on profile page, try to infer from events
        if not gender:
            for a in soup.select("a"):
                text = a.get_text(strip=True)
                if text.startswith("DS ") or text.startswith("DD "):
                    gender = "F"
                    break
                elif text.startswith("HS ") or text.startswith("HD "):
                    gender = "M"
                    break

        # Fetch ranking
        ranking = {}
        try:
            ranking_resp = s.get(f"https://badmintonsweden.tournamentsoftware.com{profile_url}/ranking", timeout=10)
            ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
            table = ranking_soup.find("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    th = row.find("th", scope="row")
                    tds = row.find_all("td")
                    if th and len(tds) >= 2:
                        category = th.get_text(strip=True)
                        if category:
                            ranking[category] = {"rank": tds[0].get_text(strip=True), "points": tds[1].get_text(strip=True)}
        except Exception:
            pass

        return jsonify(success=True, gender=gender, email=email, phone=phone, ranking=ranking)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/player-dob", methods=["GET"])
def get_player_dob():
    """Get player's date of birth from players.db (only available if they've logged in before)"""
    license_id = request.args.get("license_id", "").strip()
    if not license_id:
        return jsonify(success=True, dob="", age="")
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("SELECT dob, age FROM players WHERE license_id = ?", (license_id,))
        row = cur.fetchone()
        conn.close()
        
        if row and row[0]:
            return jsonify(success=True, dob=row[0], age=row[1] or "")
        return jsonify(success=True, dob="", age="")
    except Exception as e:
        return jsonify(success=True, dob="", age="")


@app.route("/api/player-groups", methods=["GET"])
def get_player_groups():
    """Get all player groups"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("SELECT id, group_name FROM player_groups ORDER BY group_name")
        groups = [{"id": row[0], "group_name": row[1]} for row in cur.fetchall()]
        conn.close()
        return jsonify(success=True, groups=groups)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/player-groups", methods=["POST"])
def create_player_group():
    """Create a new player group"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    group_name = data.get("group_name", "").strip()
    if not group_name:
        return jsonify(success=False, error="Group name required")
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("INSERT INTO player_groups (group_name) VALUES (?)", (group_name,))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except sqlite3.IntegrityError:
        return jsonify(success=False, error=f"Group '{group_name}' already exists")
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/player-groups/<int:group_id>", methods=["DELETE"])
def delete_player_group(group_id):
    """Delete a player group"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("DELETE FROM player_groups WHERE id = ?", (group_id,))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/komet-players", methods=["GET"])
def get_komet_players():
    """Get paginated list of komet players with optional search"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", 30))
    search = request.args.get("search", "").strip()
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        offset = (page - 1) * page_size
        
        if search:
            cur.execute("SELECT COUNT(*) FROM kometPlayers WHERE name LIKE ? OR license_id LIKE ? OR email LIKE ?",
                       (f"%{search}%", f"%{search}%", f"%{search}%"))
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT id, license_id, name, email, groups FROM kometPlayers 
                WHERE name LIKE ? OR license_id LIKE ? OR email LIKE ?
                ORDER BY name LIMIT ? OFFSET ?
            """, (f"%{search}%", f"%{search}%", f"%{search}%", page_size, offset))
        else:
            cur.execute("SELECT COUNT(*) FROM kometPlayers")
            total = cur.fetchone()[0]
            cur.execute("SELECT id, license_id, name, email, groups FROM kometPlayers ORDER BY name LIMIT ? OFFSET ?",
                       (page_size, offset))
        
        players = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(success=True, players=players, total=total)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/komet-players", methods=["POST"])
def create_komet_player():
    """Add a new komet player"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    license_id = data.get("license_id", "").strip()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    groups = data.get("groups", "").strip()
    
    # Store groups as JSON array
    if groups:
        groups_list = [g.strip() for g in groups.split(",") if g.strip()]
        groups_json = json.dumps(groups_list)
    else:
        groups_json = None
    
    if not name:
        return jsonify(success=False, error="Name required")
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("INSERT INTO kometPlayers (license_id, name, email, groups) VALUES (?, ?, ?, ?)",
                    (license_id or None, name, email or None, groups_json))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except sqlite3.IntegrityError:
        return jsonify(success=False, error=f"Player with license ID '{license_id}' already exists")
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/komet-players/<int:player_id>", methods=["PUT"])
def update_komet_player(player_id):
    """Update a komet player"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    license_id = data.get("license_id", "").strip()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    groups = data.get("groups", "").strip()
    
    # Store groups as JSON array
    if groups:
        groups_list = [g.strip() for g in groups.split(",") if g.strip()]
        groups_json = json.dumps(groups_list)
    else:
        groups_json = None
    
    if not name:
        return jsonify(success=False, error="Name required")
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("UPDATE kometPlayers SET license_id = ?, name = ?, email = ?, groups = ? WHERE id = ?",
                    (license_id or None, name, email or None, groups_json, player_id))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/komet-players/<int:player_id>", methods=["DELETE"])
def delete_komet_player(player_id):
    """Delete a komet player"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("DELETE FROM kometPlayers WHERE id = ?", (player_id,))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/allplayers-status", methods=["GET"])
def allplayers_status():
    """Get status of allplayers table (count + whether scrape is running)"""
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM allplayers")
        total = cur.fetchone()[0]
        conn.close()
        
        # Check if background thread is still running
        scraping = _allplayers_thread.is_alive() if _allplayers_thread else False
        
        return jsonify(success=True, total=total, scraping=scraping)
    except Exception as e:
        return jsonify(success=True, total=0, scraping=False)


@app.route("/api/allplayers", methods=["GET"])
def get_allplayers():
    """Get paginated list of all players with optional search"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", 50))
    search = request.args.get("search", "").strip()
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        offset = (page - 1) * page_size
        
        if search:
            cur.execute("SELECT COUNT(*) FROM allplayers WHERE name LIKE ? OR license_id LIKE ?",
                       (f"%{search}%", f"%{search}%"))
            total = cur.fetchone()[0]
            
            cur.execute("""
                SELECT license_id, name, profile_url, club FROM allplayers 
                WHERE name LIKE ? OR license_id LIKE ?
                ORDER BY name LIMIT ? OFFSET ?
            """, (f"%{search}%", f"%{search}%", page_size, offset))
        else:
            cur.execute("SELECT COUNT(*) FROM allplayers")
            total = cur.fetchone()[0]
            
            cur.execute("""
                SELECT license_id, name, profile_url, club FROM allplayers 
                ORDER BY name LIMIT ? OFFSET ?
            """, (page_size, offset))
        
        players = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        return jsonify(success=True, players=players, total=total)
    except Exception as e:
        logger.error(f"❌ Error fetching allplayers: {e}")
        return jsonify(success=False, error=str(e))


@app.route("/api/registered-emails", methods=["GET"])
def get_registered_emails():
    """Get email addresses of all registered players, optionally filtered by tournament"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    tournament = request.args.get("tournament", "").strip()
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        cur = conn.cursor()
        
        if tournament:
            cur.execute("""
                SELECT DISTINCT p.email 
                FROM tournament_registrations tr
                JOIN players_db.players p ON tr.license_id = p.license_id
                WHERE tr.tournament_name = ? AND p.email IS NOT NULL AND p.email != ''
            """, (tournament,))
        else:
            cur.execute("""
                SELECT DISTINCT p.email 
                FROM tournament_registrations tr
                JOIN players_db.players p ON tr.license_id = p.license_id
                WHERE p.email IS NOT NULL AND p.email != ''
            """)
        
        emails = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(success=True, emails=emails)
    except Exception as e:
        logger.error(f"❌ Error fetching registered emails: {e}")
        return jsonify(success=False, error=str(e))


@app.route("/api/group-emails", methods=["GET"])
def get_group_emails():
    """Get emails from kometPlayers filtered by group (or all if no group specified)"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    group = request.args.get("group", "").strip()
    
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("SELECT email, groups FROM kometPlayers WHERE email IS NOT NULL AND email != ''")
        
        emails = []
        for row in cur.fetchall():
            email, groups_json = row
            if not group:
                # No filter - return all
                emails.append(email)
            else:
                # Filter by group
                player_groups = []
                try:
                    player_groups = json.loads(groups_json) if groups_json else []
                except Exception:
                    pass
                if group in player_groups or "All" in player_groups:
                    emails.append(email)
        
        conn.close()
        return jsonify(success=True, emails=list(set(emails)))
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/send-bulk-email", methods=["POST"])
def send_bulk_email():
    """Send email to multiple recipients"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    emails = data.get("emails", [])
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    
    if not emails:
        return jsonify(success=False, error="No email addresses provided")
    if not subject or not body:
        return jsonify(success=False, error="Subject and message required")
    
    sent = 0
    failed = 0
    for email in emails:
        email = email.strip()
        if not email or "@" not in email:
            continue
        if send_email(email, subject, body) is True:
            sent += 1
        else:
            failed += 1
    
    logger.info(f"📧 Bulk email: sent={sent}, failed={failed}, subject='{subject}'")
    return jsonify(success=True, sent=sent, failed=failed, total=len(emails))


def send_email(to_email, subject, body):
    """Send an email using Brevo HTTP API (works on platforms that block SMTP ports)."""
    
    conn = sqlite3.connect(ADMIN_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM smtp_settings WHERE id=1")
    settings = cur.fetchone()
    conn.close()

    if not settings:
        logger.error("📧 ❌ No email settings found in database")
        return "No email settings found. Save settings first."
    if not settings["smtp_email"]:
        logger.error("📧 ❌ Sender email not configured")
        return "Sender email not configured."
    if not settings["smtp_password"]:
        logger.error("📧 ❌ API key not configured")
        return "API key not configured."

    sender_email = settings["smtp_email"]
    api_key = settings["smtp_password"]  # We reuse the password field for Brevo API key
    
    logger.info(f"📧 Sending email to: {to_email} (via Brevo API)")

    try:
        response = ext_requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "accept": "application/json"
            },
            json={
                "sender": {"email": sender_email, "name": "BMK Komet"},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body
            },
            timeout=15
        )
        
        if response.status_code in (200, 201):
            logger.info(f"📧 ✅ Email sent successfully to {to_email}")
            return True
        else:
            error_msg = response.json().get("message", response.text) if response.text else f"HTTP {response.status_code}"
            logger.error(f"📧 ❌ Brevo API error: {response.status_code} - {error_msg}")
            return f"Brevo API error: {error_msg}"
    except Exception as e:
        logger.error(f"📧 ❌ Email error [{type(e).__name__}]: {e}")
        return f"Error: {type(e).__name__} - {e}"


@app.route("/api/tournament-reminders", methods=["GET"])
def get_tournament_reminders():
    """Get reminder info for a tournament: schedule, registered players with emails"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    tournament_name = request.args.get("dbFile", "").strip()
    if not tournament_name:
        return jsonify(success=False, error="Tournament name required")
    
    try:
        # Get tournament info
        conn_t = sqlite3.connect(TOURNAMENTS_DB)
        cur_t = conn_t.cursor()
        cur_t.execute("SELECT admin_reg_end_date FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        row = cur_t.fetchone()
        if not row:
            conn_t.close()
            return jsonify(success=True, admin_reg_end_date="", recipients=[])
        
        admin_reg_end_date = row[0] or ""
        
        # Get registered players with their emails from players table
        conn_t.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        cur_t.execute("""
            SELECT p.name, p.email, tr.license_id
            FROM tournament_registrations tr
            LEFT JOIN players_db.players p ON tr.license_id = p.license_id
            WHERE tr.tournament_name = ? AND p.email IS NOT NULL AND p.email != ''
        """, (tournament_name,))
        
        recipients = [{"name": r[0] or "Unknown", "email": r[1]} for r in cur_t.fetchall()]
        conn_t.close()
        
        return jsonify(success=True, admin_reg_end_date=admin_reg_end_date, recipients=recipients)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/send-tournament-reminder", methods=["POST"])
def send_tournament_reminder_now():
    """Send email to all registered players in the tournament with custom subject/message"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    tournament_name = data.get("tournament_name", "").strip()
    custom_subject = data.get("subject", "").strip()
    custom_message = data.get("message", "").strip()
    
    if not tournament_name:
        return jsonify(success=False, error="Tournament name required")
    if not custom_subject or not custom_message:
        return jsonify(success=False, error="Subject and message required")
    
    try:
        # Get registered players with emails
        conn_t = sqlite3.connect(TOURNAMENTS_DB)
        conn_t.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        cur_t = conn_t.cursor()
        cur_t.execute("""
            SELECT p.name, p.email
            FROM tournament_registrations tr
            LEFT JOIN players_db.players p ON tr.license_id = p.license_id
            WHERE tr.tournament_name = ? AND p.email IS NOT NULL AND p.email != ''
        """, (tournament_name,))
        
        rows = cur_t.fetchall()
        conn_t.close()
        logger.info(f"📧 Sending to {len(rows)} registered players for {tournament_name}")
        
        sent = 0
        for name, email in rows:
            # Personalize: add greeting
            body = f"Hi {name},\n\n{custom_message}\n\nBest regards,\nBMK Komet"
            
            logger.info(f"📧 Sending to {email}...")
            result = send_email(email, custom_subject, body)
            if result is True:
                sent += 1
                logger.info(f"📧 ✅ Sent to {email}")
            else:
                logger.error(f"📧 ❌ Failed to send to {email}: {result}")
        
        return jsonify(success=True, sent=sent)
    except Exception as e:
        return jsonify(success=False, error=str(e))


def _send_admin_reg_closed_notification(tournament_name, admin_reg_end_date):
    """Send notification to all admins that a tournament's registration has closed."""
    try:
        # Get admin emails
        conn_admin = sqlite3.connect(ADMIN_DB)
        cur_admin = conn_admin.cursor()
        cur_admin.execute("SELECT username, email FROM admin_users")
        admin_emails = []
        for row in cur_admin.fetchall():
            # Use email field if set, otherwise fall back to username if it looks like email
            email = row[1] if row[1] and "@" in row[1] else (row[0] if "@" in row[0] else None)
            if email:
                admin_emails.append(email)
        
        # Check if already notified today
        from datetime import datetime
        today = datetime.now().date().isoformat()
        cur_admin.execute(
            "SELECT id FROM reminders_sent WHERE tournament_db = ? AND sent_at LIKE ?",
            (f"{tournament_name}_admin_closed", f"{today}%")
        )
        if cur_admin.fetchone():
            conn_admin.close()
            return  # Already notified today
        
        # Get registration count
        conn_t = sqlite3.connect(TOURNAMENTS_DB)
        cur_t = conn_t.cursor()
        cur_t.execute("SELECT COUNT(*) FROM tournament_registrations WHERE tournament_name = ?", (tournament_name,))
        reg_count = cur_t.fetchone()[0]
        conn_t.close()
        
        subject = f"🏸 Registration closed: {tournament_name}"
        body = (f"Hi Admin,\n\n"
                f"The Komet registration deadline for '{tournament_name}' has been reached ({admin_reg_end_date}).\n\n"
                f"📊 Total registrations: {reg_count} players\n\n"
                f"Please verify the registration details and ensure everything is in order.\n\n"
                f"You can view the registrations at: https://activitylogger.bmkkomet.se/\n\n"
                f"Best regards,\nBMK Komet System")
        
        for email in admin_emails:
            result = send_email(email, subject, body)
            if result is True:
                logger.info(f"📧 Admin notification sent to {email} for {tournament_name}")
        
        # Mark as sent
        conn_admin.execute(
            "INSERT INTO reminders_sent (tournament_db, player_email, sent_at) VALUES (?,?,?)",
            (f"{tournament_name}_admin_closed", "admin", datetime.now().isoformat())
        )
        conn_admin.commit()
        conn_admin.close()
    except Exception as e:
        logger.error(f"❌ Error sending admin notification: {e}")


def send_reminders():
    """
    Auto-email reminders to eligible players (based on tournament groups).
    Sends at 7 days and 3 days before admin_reg_end_date.
    Skips players already registered for the tournament.
    """
    from datetime import datetime, timedelta

    logger.info("📧 Checking for reminder emails to send...")
    
    today = datetime.now().date()
    
    try:
        # Get all selected tournaments with admin_reg_end_date
        conn_t = sqlite3.connect(TOURNAMENTS_DB)
        cur_t = conn_t.cursor()
        cur_t.execute("""
            SELECT tournament_name, admin_reg_end_date, tournament_groups
            FROM tournaments 
            WHERE selected_for_view = 1 AND admin_reg_end_date IS NOT NULL AND admin_reg_end_date != ''
        """)
        tournaments = cur_t.fetchall()
        
        for tournament_name, admin_reg_end_date, tournament_groups_json in tournaments:
            try:
                reg_close = datetime.strptime(admin_reg_end_date, "%Y-%m-%d").date()
            except Exception:
                continue
            
            days_left = (reg_close - today).days
            
            # Send admin notification on the day registration closes
            if days_left == 0:
                _send_admin_reg_closed_notification(tournament_name, admin_reg_end_date)
            
            # Only send player reminders at 7 days or 3 days before close
            if days_left not in (7, 3):
                continue
            
            reminder_type = f"{days_left}days"
            
            # Get tournament groups
            tournament_groups = []
            try:
                tournament_groups = json.loads(tournament_groups_json) if tournament_groups_json else []
            except Exception:
                pass
            
            # Get registered player license_ids for this tournament (to skip them)
            cur_t.execute(
                "SELECT license_id FROM tournament_registrations WHERE tournament_name = ?",
                (tournament_name,)
            )
            registered_ids = {row[0] for row in cur_t.fetchall()}
            
            # Get eligible players from kometPlayers
            conn_p = sqlite3.connect(PLAYERS_DB)
            cur_p = conn_p.cursor()
            cur_p.execute("SELECT name, license_id, email, groups FROM kometPlayers WHERE email IS NOT NULL AND email != ''")
            
            sent_count = 0
            for p_row in cur_p.fetchall():
                player_name, license_id, email, player_groups_json = p_row
                
                # Skip if already registered
                if license_id in registered_ids:
                    continue
                
                # Check group eligibility
                player_groups = []
                try:
                    player_groups = json.loads(player_groups_json) if player_groups_json else []
                except Exception:
                    pass
                
                if tournament_groups:
                    if "All" not in tournament_groups and "all" not in tournament_groups and not set(player_groups).intersection(set(tournament_groups)):
                        continue  # Player's groups don't match
                
                # Check if player opted out of reminders for this tournament
                cur_t.execute("SELECT id FROM reminder_opt_out WHERE license_id = ? AND tournament_name = ?",
                             (license_id, tournament_name))
                if cur_t.fetchone():
                    continue  # Player opted out
                
                # Check if reminder already sent for this type
                conn_admin = sqlite3.connect(ADMIN_DB)
                cur_admin = conn_admin.cursor()
                cur_admin.execute(
                    "SELECT id FROM reminders_sent WHERE tournament_db = ? AND player_email = ? AND sent_at LIKE ?",
                    (f"{tournament_name}_{reminder_type}", email, f"{today.isoformat()}%")
                )
                if cur_admin.fetchone():
                    conn_admin.close()
                    continue  # Already sent today
                
                # Build email
                if days_left == 7:
                    subject = f"📋 Registration closing in 1 week: {tournament_name}"
                    body = (f"Hi {player_name},\n\n"
                            f"This is a friendly reminder that registration for '{tournament_name}' "
                            f"closes in 1 week ({admin_reg_end_date}).\n\n"
                            f"Don't forget to register if you want to participate!\n\n"
                            f"Best regards,\nBMK Komet")
                else:
                    subject = f"⚠️ Last chance to register: {tournament_name} (3 days left!)"
                    body = (f"Hi {player_name},\n\n"
                            f"⚠️ Registration for '{tournament_name}' closes in 3 days ({admin_reg_end_date})!\n\n"
                            f"If you haven't registered yet, please do so soon.\n\n"
                            f"Best regards,\nBMK Komet")
                
                # Send
                result = send_email(email, subject, body)
                if result is True:
                    conn_admin.execute(
                        "INSERT INTO reminders_sent (tournament_db, player_email, sent_at) VALUES (?,?,?)",
                        (f"{tournament_name}_{reminder_type}", email, datetime.now().isoformat())
                    )
                    conn_admin.commit()
                    sent_count += 1
                    logger.info(f"📧 Reminder sent to {email} for {tournament_name} ({days_left} days left)")
                
                conn_admin.close()
            
            conn_p.close()
            
            if sent_count > 0:
                logger.info(f"📧 Sent {sent_count} reminders for {tournament_name} ({days_left} days before close)")
        
        conn_t.close()
    except Exception as e:
        logger.error(f"❌ Error in send_reminders: {e}")
    
    # COMPETITION DATE REMINDERS: 7 days and 3 days before competition_start
    # Sent to REGISTERED players only
    try:
        conn_t = sqlite3.connect(TOURNAMENTS_DB)
        conn_t.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        cur_t = conn_t.cursor()
        
        cur_t.execute("""
            SELECT tournament_name, competition_start, date_start
            FROM tournaments 
            WHERE selected_for_view = 1 
            AND (competition_start IS NOT NULL AND competition_start != '' 
                 OR date_start IS NOT NULL AND date_start != '')
        """)
        
        for tournament_name, competition_start, date_start in cur_t.fetchall():
            comp_date_str = competition_start or date_start
            if not comp_date_str:
                continue
            
            try:
                comp_date = datetime.strptime(comp_date_str, "%Y-%m-%d").date()
            except Exception:
                continue
            
            days_until_comp = (comp_date - today).days
            
            if days_until_comp not in (7, 3):
                continue
            
            reminder_type = f"comp_{days_until_comp}days"
            
            # Get registered players with emails
            cur_t.execute("""
                SELECT p.name, p.email, tr.license_id
                FROM tournament_registrations tr
                LEFT JOIN players_db.players p ON tr.license_id = p.license_id
                WHERE tr.tournament_name = ? AND p.email IS NOT NULL AND p.email != ''
            """, (tournament_name,))
            
            for name, email, license_id in cur_t.fetchall():
                # Check opt-out
                cur_t.execute("SELECT id FROM reminder_opt_out WHERE license_id = ? AND tournament_name = ?",
                             (license_id, tournament_name))
                if cur_t.fetchone():
                    continue
                
                # Check if already sent
                conn_admin = sqlite3.connect(ADMIN_DB)
                cur_admin = conn_admin.cursor()
                cur_admin.execute(
                    "SELECT id FROM reminders_sent WHERE tournament_db = ? AND player_email = ? AND sent_at LIKE ?",
                    (f"{tournament_name}_{reminder_type}", email, f"{today.isoformat()}%")
                )
                if cur_admin.fetchone():
                    conn_admin.close()
                    continue
                
                # Build email
                if days_until_comp == 7:
                    subject = f"🏸 {tournament_name} starts in 1 week!"
                    body = (f"Hi {name},\n\n"
                            f"Just a reminder that '{tournament_name}' starts in 1 week ({comp_date_str}).\n\n"
                            f"Make sure you're prepared and have everything you need!\n\n"
                            f"Good luck! 🏸\n\n"
                            f"Best regards,\nBMK Komet")
                else:
                    subject = f"🏸 {tournament_name} starts in 3 days!"
                    body = (f"Hi {name},\n\n"
                            f"'{tournament_name}' is just 3 days away ({comp_date_str})!\n\n"
                            f"Final preparations time — good luck! 🏸\n\n"
                            f"Best regards,\nBMK Komet")
                
                result = send_email(email, subject, body)
                if result is True:
                    conn_admin.execute(
                        "INSERT INTO reminders_sent (tournament_db, player_email, sent_at) VALUES (?,?,?)",
                        (f"{tournament_name}_{reminder_type}", email, datetime.now().isoformat())
                    )
                    conn_admin.commit()
                    logger.info(f"📧 Competition reminder sent to {email} for {tournament_name} ({days_until_comp} days)")
                conn_admin.close()
        
        conn_t.close()
    except Exception as e:
        logger.error(f"❌ Error in competition reminders: {e}")


# --- Results Page ---
@app.route("/results.html")
def results_page():
    from flask import render_template
    return render_template("results.html")


@app.route("/api/search-tournaments", methods=["GET"])
def search_tournaments():
    """Search tournaments by date range and status."""
    try:
        import re
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        status = request.args.get("status", "")  # 2=reg open, 3=upcoming, 4=finished

        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        start_fmt = f"{start}T00:00" if start else ""
        end_fmt = f"{end}T00:00" if end else ""

        url = f"https://badmintonsweden.tournamentsoftware.com/find?DateFilterType=0&StartDate={start_fmt}&EndDate={end_fmt}&Distance=10&page=1&SportID=2"
        if status:
            url += f"&StatusFilterID={status}"

        resp = s.get(url, timeout=10)
        page_soup = BeautifulSoup(resp.text, "html.parser")
        form = page_soup.select_one("#form_globalsearch")
        form_data = {}
        if form:
            for inp in form.find_all("input"):
                name = inp.get("name", "")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value
        if status:
            form_data["TournamentExtendedFilter.StatusFilterID"] = status

        resp = s.post("https://badmintonsweden.tournamentsoftware.com/find/tournament/DoSearch",
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        tournaments = []
        for item in soup.select("li.list__item"):
            link = item.select_one("a.media__link")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href", "")
            location_el = item.select_one(".media__subheading .nav-link__value")
            location = location_el.get_text(strip=True) if location_el else ""
            time_els = item.select("time")
            date_start = time_els[0].get("datetime", "")[:10] if time_els else ""
            date_end = time_els[1].get("datetime", "")[:10] if len(time_els) > 1 else ""
            status_el = item.select_one(".tournament-status, .media__status")
            status_text = status_el.get_text(strip=True) if status_el else ""
            tid_match = re.search(r'id=([A-Fa-f0-9-]+)', href)
            tid = tid_match.group(1) if tid_match else ""

            tournaments.append({
                "id": tid,
                "name": name,
                "location": location,
                "date_start": date_start,
                "date_end": date_end,
                "status": status_text
            })

        return jsonify(success=True, tournaments=tournaments)
    except Exception as e:
        return jsonify(success=False, error=str(e), tournaments=[]), 500


@app.route("/tournament-detail.html")
def tournament_detail_page():
    from flask import render_template
    return render_template("tournament_detail.html")


@app.route("/api/tournament-medals", methods=["GET"])
def tournament_medals():
    """Get medal winners from tournament winners page."""
    try:
        import re
        tournament_id = request.args.get("id", "")
        if not tournament_id:
            return jsonify(success=False, error="No tournament ID"), 400

        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/sport/winners.aspx?id={tournament_id}", timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        medals = []
        for table in soup.find_all("table"):
            event_name = ""
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) == 1:
                    event_name = cells[0].get_text(strip=True)
                    continue
                if len(cells) >= 2:
                    placement = cells[0].get_text(strip=True)
                    player_links = cells[1].find_all("a")
                    for a in player_links:
                        txt = a.get_text(strip=True)
                        if txt and not re.match(r"^\[.*\]$", txt) and len(txt) > 3:
                            clean = re.sub(r"\s*\[\d+(/\d+)?\]\s*$", "", txt).strip()
                            if clean:
                                medals.append({"name": clean, "event": event_name, "placement": placement})

        return jsonify(success=True, medals=medals)
    except Exception as e:
        return jsonify(success=False, error=str(e), medals=[]), 500


@app.route("/api/tournament-player-id", methods=["GET"])
def tournament_player_id():
    """Find a player's ID from the tournament player list by name."""
    try:
        tournament_id = request.args.get("id", "")
        name = request.args.get("name", "")

        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/tournament/{tournament_id}/Players/GetPlayersContent",
            headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        import re
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) == name or name in a.get_text(strip=True):
                href = a.get("href", "")
                match = re.search(r"player=(\d+)", href)
                if match:
                    return jsonify(success=True, player_id=match.group(1))

        return jsonify(success=True, player_id="")
    except Exception as e:
        return jsonify(success=False, error=str(e), player_id=""), 500


@app.route("/api/tournament-player-results", methods=["GET"])
def tournament_player_results():
    """Get a player's match results from the tournament."""
    try:
        tournament_id = request.args.get("id", "")
        player_id = request.args.get("player", "")
        if not tournament_id or not player_id:
            return jsonify(success=False, error="Missing parameters"), 400

        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/tournament/{tournament_id}/player/{player_id}", timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse stats table
        stats = []
        stats_table = soup.select_one("table")
        if stats_table:
            for row in stats_table.select("tr")[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                if len(cells) >= 5:
                    stats.append({
                        "category": cells[0],
                        "played": cells[1],
                        "win_loss": cells[2],
                        "sets": cells[3],
                        "points": cells[4]
                    })

        # Parse matches
        matches = []
        for match_el in soup.select(".match"):
            # Round and event
            header_items = match_el.select(".match__header-title-item .nav-link__value")
            round_name = header_items[0].get_text(strip=True) if header_items else ""
            event = header_items[1].get_text(strip=True) if len(header_items) > 1 else ""

            # Teams
            rows = match_el.select(".match__row")
            team1 = ""
            team2 = ""
            team1_won = False
            for i, row in enumerate(rows):
                players = [el.get_text(strip=True) for el in row.select(".nav-link__value") if el.get_text(strip=True)]
                is_won = "has-won" in row.get("class", [])
                name = " / ".join(players) if players else row.get_text(strip=True).strip()
                if i == 0:
                    team1 = name
                    team1_won = is_won
                else:
                    team2 = name

            # Scores from ul.points > li.points__cell
            score_sets = []
            points_lists = match_el.select("ul.points")
            for pts in points_lists:
                cells = pts.select("li.points__cell")
                if len(cells) == 2:
                    score_sets.append(f"{cells[0].get_text(strip=True)}-{cells[1].get_text(strip=True)}")

            if team1 or team2:
                matches.append({
                    "round": round_name,
                    "event": event,
                    "team1": team1,
                    "team2": team2,
                    "team1_won": team1_won,
                    "score": " ".join(score_sets)
                })

        return jsonify(success=True, stats=stats, matches=matches)
    except Exception as e:
        return jsonify(success=False, error=str(e), stats=[], matches=[]), 500


@app.route("/api/tournament-clubs", methods=["GET"])
def tournament_clubs():
    """Get all players and their clubs from a tournament's player list."""
    try:
        tournament_id = request.args.get("id", "")
        if not tournament_id:
            return jsonify(success=False, error="No tournament ID"), 400

        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        url = f"https://badmintonsweden.tournamentsoftware.com/tournament/{tournament_id}/Players/GetPlayersContent"
        resp = s.get(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        players = []
        for item in soup.select("li"):
            name_el = item.select_one("a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue
            # Get player ID from href
            import re as re_mod
            href = name_el.get("href", "")
            pid_match = re_mod.search(r"player=(\d+)", href)
            player_id = pid_match.group(1) if pid_match else ""
            # Club is the text in the li that's not the player name
            all_text = [t.strip() for t in item.get_text(separator="|", strip=True).split("|") if t.strip()]
            club = ""
            for t in all_text:
                if t != name and len(t) > 2 and not t.startswith("("):
                    club = t
                    break
            players.append({"name": name, "club": club, "player_id": player_id})

        # Deduplicate
        seen = set()
        unique_players = []
        for p in players:
            key = p["name"]
            if key not in seen:
                seen.add(key)
                unique_players.append(p)

        return jsonify(success=True, players=unique_players)
    except Exception as e:
        return jsonify(success=False, error=str(e), players=[]), 500


# ==================== DATABASE VIEWER ENDPOINTS ====================

@app.route("/api/databases", methods=["GET"])
def api_get_databases():
    """Get list of all databases"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    try:
        from db_viewer import get_database_list, get_database_statistics
        
        logger.info("📊 Admin viewing database list")
        databases = get_database_list()
        stats = get_database_statistics()
        
        logger.debug(f"📊 Returning {len(databases)} databases")
        return jsonify(success=True, databases=databases, statistics=stats)
    
    except Exception as e:
        logger.error(f"❌ Error fetching databases: {str(e)}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/database/<db_name>/tables", methods=["GET"])
def api_get_tables(db_name):
    """Get list of tables in a database"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    try:
        from db_viewer import get_database_list, get_tables_in_database
        
        logger.info(f"📋 Admin viewing tables in {db_name}")
        
        # Get database path
        databases = get_database_list()
        db_path = next((db["path"] for db in databases if db["name"] == db_name), None)
        
        if not db_path or not os.path.exists(db_path):
            logger.error(f"❌ Database not found: {db_name}")
            return jsonify(success=False, error="Database not found"), 404
        
        tables = get_tables_in_database(db_path)
        logger.debug(f"📋 Found {len(tables)} tables in {db_name}")
        
        return jsonify(success=True, database=db_name, tables=tables)
    
    except Exception as e:
        logger.error(f"❌ Error fetching tables from {db_name}: {str(e)}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/database/<db_name>/table/<table_name>", methods=["GET"])
def api_get_table_data(db_name, table_name):
    """Get table data with pagination"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    try:
        from db_viewer import get_database_list, get_table_data
        
        # Get parameters
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 10, type=int)
        search = request.args.get("search", None, type=str)
        
        logger.info(f"📖 Admin viewing {db_name}.{table_name} (page {page})")
        
        # Limit page size for security
        page_size = min(page_size, 100)
        page = max(page, 1)
        
        # Get database path
        databases = get_database_list()
        db_path = next((db["path"] for db in databases if db["name"] == db_name), None)
        
        if not db_path or not os.path.exists(db_path):
            logger.error(f"❌ Database not found: {db_name}")
            return jsonify(success=False, error="Database not found"), 404
        
        # Get table data
        result = get_table_data(db_path, table_name, page=page, page_size=page_size, search=search)
        
        if "error" in result:
            logger.error(f"❌ Error fetching table data: {result['error']}")
            return jsonify(success=False, error=result["error"]), 500
        
        logger.debug(f"📖 Returning {len(result['rows'])} rows from {table_name}")
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"❌ Error fetching table {table_name}: {str(e)}")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/database/<db_name>/table/<table_name>/export", methods=["GET"])
def api_export_table(db_name, table_name):
    """Export table data as JSON or CSV"""
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    try:
        from db_viewer import get_database_list, export_table_as_json, export_table_as_csv
        
        # Get parameters
        format_type = request.args.get("format", "json", type=str).lower()
        limit = request.args.get("limit", None, type=int)
        
        logger.info(f"📤 Admin exporting {db_name}.{table_name} as {format_type}")
        
        # Get database path
        databases = get_database_list()
        db_path = next((db["path"] for db in databases if db["name"] == db_name), None)
        
        if not db_path or not os.path.exists(db_path):
            logger.error(f"❌ Database not found: {db_name}")
            return jsonify(success=False, error="Database not found"), 404
        
        # Export data
        if format_type == "csv":
            data = export_table_as_csv(db_path, table_name, limit=limit)
            response_headers = {
                'Content-Disposition': f'attachment; filename="{table_name}.csv"'
            }
            logger.info(f"✅ Exported {table_name} as CSV")
            return data, 200, response_headers
        else:  # json
            data = export_table_as_json(db_path, table_name, limit=limit)
            response_headers = {
                'Content-Disposition': f'attachment; filename="{table_name}.json"'
            }
            logger.info(f"✅ Exported {table_name} as JSON")
            return data, 200, response_headers
    
    except Exception as e:
        logger.error(f"❌ Error exporting {table_name}: {str(e)}")
        return jsonify(success=False, error=str(e)), 500


def reminder_scheduler():
    """Run reminders check every 6 hours."""
    import time
    while True:
        try:
            send_reminders()
        except Exception as e:
            print(f"[Scheduler Error] {e}")
        time.sleep(6 * 3600)  # Check every 6 hours


if __name__ == "__main__":
    import threading
    threading.Thread(target=reminder_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=3000, debug=True, use_reloader=False)
