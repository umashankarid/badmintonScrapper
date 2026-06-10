import os
import json
import sqlite3
import requests as ext_requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, session, send_from_directory

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "supersecretkey"

TOURNAMENTS_DIR = os.path.join(os.path.dirname(__file__), "tournaments")
os.makedirs(TOURNAMENTS_DIR, exist_ok=True)
PLAYERS_DB = os.path.join(os.path.dirname(__file__), "players.db")


POINTS_DB = os.path.join(os.path.dirname(__file__), "point_rules.db")
ADMIN_DB = os.path.join(os.path.dirname(__file__), "admin.db")


def init_admin_db():
    conn = sqlite3.connect(ADMIN_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL
        )
    """)
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
    conn.close()


init_admin_db()


def is_admin_user(username):
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM admins WHERE username=?", (username,))
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


def get_tournament_db(db_file):
    path = os.path.join(TOURNAMENTS_DIR, db_file)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    # Auto-migrate: add missing columns
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(players)")
    columns = [col[1] for col in cur.fetchall()]
    if "player_id" in columns:
        if "license_id" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN license_id TEXT DEFAULT ''")
        if "email" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN email TEXT DEFAULT ''")
        if "phone" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN phone TEXT DEFAULT ''")
        if "ranking" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN ranking TEXT DEFAULT ''")
        if "dob" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN dob TEXT DEFAULT ''")
        if "age" not in columns:
            conn.execute("ALTER TABLE players ADD COLUMN age TEXT DEFAULT ''")
        conn.commit()
    return conn


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
        valid_categories = {"DS", "HS", "DD", "HD", "MD"}
        for row in table.find_all("tr")[1:]:
            th = row.find("th", scope="row")
            tds = row.find_all("td")
            if th and len(tds) >= 2:
                category = th.get_text(strip=True)
                if category in valid_categories:
                    rank = tds[0].get_text(strip=True)
                    points = tds[1].get_text(strip=True)
                    ranking[category] = {"rank": rank, "points": points}
        return json.dumps(ranking) if ranking else ""
    except Exception:
        return ""


def init_players_db():
    conn = sqlite3.connect(PLAYERS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            profile_url TEXT UNIQUE,
            club TEXT,
            gender TEXT
        )
    """)
    conn.commit()
    conn.close()


init_players_db()


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


@app.route("/login.html")
def login_page():
    return send_from_directory("templates", "login.html")


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
                valid_categories = {"DS", "HS", "DD", "HD", "MD"}
                for row in table.find_all("tr")[1:]:
                    th = row.find("th", scope="row")
                    tds = row.find_all("td")
                    if th and len(tds) >= 2:
                        category = th.get_text(strip=True)
                        if category in valid_categories:
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
                    return jsonify(success=True, allowed=False, age_restriction=False,
                        message=f"Player is {age_at_comp} years old. {level} is for players under {age_limit}.")

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
                return jsonify(success=True, allowed=False, age_restriction=False,
                    message=f"Player is {age_at_comp} years old. Cannot play {level} (too old). Should play U{correct_group} or higher.")

        except Exception:
            pass

        # No point restrictions for age-based levels
        return jsonify(success=True, allowed=True)

    if level.startswith("U"):
        return jsonify(success=True, allowed=True)

    # Adult classes: Elit, A, B, C, D
    # Kids can only play adult classes (B, A, Elit) after they turn 13
    # AND only after June of the year they turn 13
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
    elif max_pts is not None and points > max_pts:
        blocked = True
        message = f"Your {category} points ({points}) exceed the maximum ({max_pts}) for class {level}."

    return jsonify(success=True, allowed=not blocked, message=message)


@app.route("/api/admin-exists", methods=["GET"])
def admin_exists():
    return jsonify(exists=True)


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
        conn.execute("INSERT INTO admins (username) VALUES (?)", (username,))
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
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username:
        return jsonify(success=False, error="Username required"), 400
    if password != "admin@2026":
        return jsonify(success=False, error="Incorrect confirmation password"), 403
    conn = sqlite3.connect(ADMIN_DB)
    conn.execute("DELETE FROM admins WHERE username=?", (username,))
    conn.commit()
    conn.close()
    # If removed self, update session
    if username == session.get("bwf_login"):
        session["admin"] = False
    return jsonify(success=True)


@app.route("/admin/list-admins", methods=["GET"])
def list_admins():
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    cur.execute("SELECT username FROM admins ORDER BY username")
    admins = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify(success=True, admins=admins)


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
    if result:
        return jsonify(success=True, message="Test email sent!")
    return jsonify(success=False, error="Failed to send email. Check SMTP settings."), 500


# --- Tournament CRUD ---
@app.route("/api/tournaments", methods=["GET"])
def list_tournaments():
    if not os.path.exists(TOURNAMENTS_DIR):
        return jsonify([])
    files = [f for f in os.listdir(TOURNAMENTS_DIR) if f.endswith(".db")]
    tournaments = []
    for f in files:
        conn = get_tournament_db(f)
        if not conn:
            continue
        cur = conn.cursor()
        try:
            cur.execute("SELECT name, levels, competition_date, final_registration_date, final_cancellation_date FROM tournaments LIMIT 1")
            row = cur.fetchone()
            if row:
                levels = json.loads(row[1]) if row[1] else []
                tournaments.append({
                    "name": row[0],
                    "db": f,
                    "levels": levels,
                    "competition_date": row[2],
                    "final_registration_date": row[3],
                    "final_cancellation_date": row[4],
                })
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return jsonify(tournaments)


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
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    name = data.get("name")
    levels = data.get("levels", [])
    bwf_url = data.get("bwf_url", "")
    registration_opens = data.get("registration_opens", "")
    final_registration_date = data.get("final_registration_date", "")
    final_cancellation_date = data.get("final_cancellation_date", "")
    competition_date = data.get("competition_date", "")
    competition_end = data.get("competition_end", "")

    if not name:
        return jsonify(success=False, error="Name required"), 400

    db_file = name.lower().replace(" ", "_") + ".db"
    db_path = os.path.join(TOURNAMENTS_DIR, db_file)

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            bwf_url TEXT,
            levels TEXT,
            registration_opens TEXT,
            final_registration_date TEXT,
            final_cancellation_date TEXT,
            competition_date TEXT,
            competition_end TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT,
            license_id TEXT,
            club TEXT,
            gender TEXT,
            email TEXT,
            phone TEXT,
            ranking TEXT,
            singles_levels TEXT,
            doubles_levels TEXT,
            mixed_levels TEXT,
            doubles_partner TEXT,
            mixed_partner TEXT
        )
    """)
    conn.execute(
        "INSERT INTO tournaments (name, bwf_url, levels, registration_opens, final_registration_date, final_cancellation_date, competition_date, competition_end) VALUES (?,?,?,?,?,?,?,?)",
        (name, bwf_url, json.dumps(levels), registration_opens, final_registration_date, final_cancellation_date, competition_date, competition_end)
    )
    conn.commit()
    conn.close()
    return jsonify(success=True, db=db_file)


@app.route("/admin/delete-tournament", methods=["POST"])
def delete_tournament():
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    data = request.json
    db_file = data.get("db")
    if not db_file:
        return jsonify(success=False, error="db required"), 400
    path = os.path.join(TOURNAMENTS_DIR, db_file)
    if os.path.exists(path):
        os.remove(path)
    return jsonify(success=True)


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
    return jsonify(success=True)


# --- Tournament info ---
@app.route("/api/open-tournaments", methods=["GET"])
def open_tournaments():
    """Fetch tournaments with open registration from Badminton Sweden."""
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

        return jsonify(success=True, tournaments=tournaments)
    except Exception as e:
        return jsonify(success=False, error=str(e), tournaments=[]), 500


@app.route("/api/my-registrations", methods=["GET"])
def my_registrations():
    """Check which tournaments the logged-in player is registered in."""
    player_name = session.get("bwf_player")
    if not player_name:
        return jsonify(success=False, registered_urls=[])

    registered_urls = []
    if not os.path.exists(TOURNAMENTS_DIR):
        return jsonify(success=True, registered_urls=[])

    for f in os.listdir(TOURNAMENTS_DIR):
        if not f.endswith(".db"):
            continue
        conn = get_tournament_db(f)
        if not conn:
            continue
        try:
            cur = conn.cursor()
            cur.execute("SELECT bwf_url FROM tournaments LIMIT 1")
            row = cur.fetchone()
            if row and row[0]:
                cur.execute("SELECT player_id FROM players WHERE player_name=?", (player_name,))
                if cur.fetchone():
                    registered_urls.append(row[0])
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return jsonify(success=True, registered_urls=registered_urls)


@app.route("/api/ensure-tournament", methods=["POST"])
def ensure_tournament():
    """Auto-create tournament DB from BWF URL if it doesn't exist."""
    data = request.json
    url = data.get("url", "")
    if not url:
        return jsonify(success=False, error="URL required"), 400

    # Check if we already have this tournament
    if os.path.exists(TOURNAMENTS_DIR):
        for f in os.listdir(TOURNAMENTS_DIR):
            if not f.endswith(".db"):
                continue
            conn = get_tournament_db(f)
            if not conn:
                continue
            try:
                cur = conn.cursor()
                cur.execute("SELECT bwf_url FROM tournaments LIMIT 1")
                row = cur.fetchone()
                if row and row[0] == url:
                    conn.close()
                    return jsonify(success=True, db=f)
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()

    # Fetch tournament info from BWF
    try:
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

        # Get levels
        import re
        levels = []
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

        if not name:
            return jsonify(success=False, error="Could not fetch tournament info"), 500

        # Create the DB
        db_file = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') + ".db"
        db_path = os.path.join(TOURNAMENTS_DIR, db_file)

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                bwf_url TEXT,
                levels TEXT,
                registration_opens TEXT,
                final_registration_date TEXT,
                final_cancellation_date TEXT,
                competition_date TEXT,
                competition_end TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                license_id TEXT,
                club TEXT,
                gender TEXT,
                email TEXT,
                phone TEXT,
                ranking TEXT,
                singles_levels TEXT,
                doubles_levels TEXT,
                mixed_levels TEXT,
                doubles_partner TEXT,
                mixed_partner TEXT
            )
        """)
        conn.execute(
            "INSERT INTO tournaments (name, bwf_url, levels, registration_opens, final_registration_date, final_cancellation_date, competition_date, competition_end) VALUES (?,?,?,?,?,?,?,?)",
            (name, url, json.dumps(levels), dates.get("registration_opens", ""),
             dates.get("registration_closes", ""), dates.get("cancellation_deadline", ""),
             dates.get("competition_start", ""), dates.get("competition_end", ""))
        )
        conn.commit()
        conn.close()
        return jsonify(success=True, db=db_file)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/tournament-events", methods=["GET"])
def get_tournament_events():
    """Fetch event classes from Badminton Sweden for a tournament."""
    db_file = request.args.get("dbFile")
    if not db_file:
        return jsonify(success=False, error="dbFile required"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404
    cur = conn.cursor()
    try:
        cur.execute("SELECT bwf_url FROM tournaments LIMIT 1")
        row = cur.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()

    if not row or not row[0]:
        # No BWF URL - fall back to levels stored in DB
        conn = get_tournament_db(db_file)
        cur = conn.cursor()
        cur.execute("SELECT levels FROM tournaments LIMIT 1")
        lrow = cur.fetchone()
        conn.close()
        levels = json.loads(lrow[0]) if lrow and lrow[0] else []
        # Generate generic events from levels
        singles = [f"HS {l}" for l in levels] + [f"DS {l}" for l in levels]
        doubles = [f"HD {l}" for l in levels] + [f"DD {l}" for l in levels]
        mixed = [f"MD {l}" for l in levels]
        return jsonify(success=True, events=singles+doubles+mixed, singles=singles, doubles=doubles, mixed=mixed)

    bwf_url = row[0]
    import re
    tid_match = re.search(r'/tournament/([^/]+)', bwf_url)
    if not tid_match:
        return jsonify(success=False, error="Invalid BWF URL"), 400

    try:
        s = ext_requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        tid = tid_match.group(1)
        resp = s.get(f"https://badmintonsweden.tournamentsoftware.com/sport/events.aspx?id={tid}", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        for a in soup.select("a"):
            text = a.get_text(strip=True)
            if text and len(text) < 50 and any(cat in text for cat in ["HS", "DS", "HD", "DD", "MD"]):
                events.append(text)

        singles = [e for e in events if e.startswith("HS") or e.startswith("DS")]
        doubles = [e for e in events if e.startswith("HD") or e.startswith("DD")]
        mixed = [e for e in events if e.startswith("MD")]

        return jsonify(success=True, events=events, singles=singles, doubles=doubles, mixed=mixed)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/tournament", methods=["GET"])
def get_tournament_info():
    db_file = request.args.get("dbFile")
    if not db_file:
        return jsonify(success=False, error="dbFile required"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404
    cur = conn.cursor()
    try:
        cur.execute("SELECT name, levels, competition_date FROM tournaments LIMIT 1")
        row = cur.fetchone()
    except sqlite3.OperationalError:
        cur.execute("SELECT name, levels FROM tournaments LIMIT 1")
        row = cur.fetchone()
        row = (row[0], row[1], "") if row else None
    conn.close()
    if not row:
        return jsonify(success=False, error="No tournament info"), 500
    levels = json.loads(row[1]) if row[1] else []
    return jsonify(success=True, tournament={"name": row[0], "levels": levels, "competition_date": row[2] or ""})


# --- Players in tournament ---
@app.route("/api/tournament-players", methods=["GET"])
def get_tournament_players():
    db_file = request.args.get("dbFile")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", 20))
    if not db_file:
        return jsonify(success=False, error="dbFile required"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players")
    total = cur.fetchone()[0]
    offset = (page - 1) * page_size
    cur.execute("SELECT * FROM players LIMIT ? OFFSET ?", (page_size, offset))
    players = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(success=True, total=total, players=players)


@app.route("/api/add-player", methods=["POST"])
def add_player():
    data = request.json
    db_file = data.get("dbFile")
    player = data.get("player")
    if not db_file or not player:
        return jsonify(success=False, error="Missing data"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404

    player_id = player.get("player_id")
    if not player_id and not player.get("club", "").strip():
        conn.close()
        return jsonify(success=False, error="Club is required"), 400

    # Check if player already exists by license_id or name
    if not player_id:
        license_id = player.get("license_id", "").strip()
        if license_id:
            existing = conn.execute("SELECT player_id FROM players WHERE license_id=?", (license_id,)).fetchone()
            if existing:
                player_id = existing[0]
        if not player_id:
            existing = conn.execute("SELECT player_id FROM players WHERE player_name=?", (player["player_name"],)).fetchone()
            if existing:
                player_id = existing[0]

    if player_id:
        # Merge levels with existing entry
        existing_row = conn.execute("SELECT singles_levels, doubles_levels, mixed_levels, doubles_partner, mixed_partner FROM players WHERE player_id=?", (player_id,)).fetchone()
        if existing_row:
            def merge_levels(existing, new):
                existing_set = set(filter(None, (existing or "").split(",")))
                new_set = set(filter(None, (new or "").split(",")))
                merged = existing_set | new_set
                return ",".join(sorted(merged)) if merged else ""

            merged_singles = merge_levels(existing_row[0], player.get("singles_levels", ""))
            merged_doubles = merge_levels(existing_row[1], player.get("doubles_levels", ""))
            merged_mixed = merge_levels(existing_row[2], player.get("mixed_levels", ""))
            new_doubles_partner = player.get("doubles_partner", "").strip()
            new_mixed_partner = player.get("mixed_partner", "").strip()
            old_doubles_partner = (existing_row[3] or "").strip()
            old_mixed_partner = (existing_row[4] or "").strip()

            # Partner is only "changed" if a different non-empty name was submitted
            doubles_partner_changed = (new_doubles_partner and new_doubles_partner != old_doubles_partner)
            mixed_partner_changed = (new_mixed_partner and new_mixed_partner != old_mixed_partner)

            # If doubles partner changed, clear old partner's reference
            if old_doubles_partner and doubles_partner_changed:
                conn.execute(
                    "UPDATE players SET doubles_partner='', doubles_levels='' WHERE player_name=? AND doubles_partner=?",
                    (old_doubles_partner, player["player_name"])
                )

            # If mixed partner changed, clear old partner's reference
            if old_mixed_partner and mixed_partner_changed:
                conn.execute(
                    "UPDATE players SET mixed_partner='', mixed_levels='' WHERE player_name=? AND mixed_partner=?",
                    (old_mixed_partner, player["player_name"])
                )

            # Keep old partner if new one wasn't provided
            doubles_partner_final = new_doubles_partner if doubles_partner_changed else old_doubles_partner
            mixed_partner_final = new_mixed_partner if mixed_partner_changed else old_mixed_partner

            conn.execute(
                "UPDATE players SET player_name=?, license_id=?, club=?, gender=?, email=?, phone=?, dob=?, age=?, ranking=?, singles_levels=?, doubles_levels=?, mixed_levels=?, doubles_partner=?, mixed_partner=? WHERE player_id=?",
                (player["player_name"], player.get("license_id", ""), player["club"], player["gender"],
                 player.get("email", ""), player.get("phone", ""), player.get("dob", ""), player.get("age", ""), player.get("ranking", ""),
                 merged_singles, merged_doubles, merged_mixed, doubles_partner_final, mixed_partner_final, player_id)
            )

            # Remove players who now have no categories left
            conn.execute("""
                DELETE FROM players WHERE
                    (singles_levels IS NULL OR singles_levels = '') AND
                    (doubles_levels IS NULL OR doubles_levels = '') AND
                    (mixed_levels IS NULL OR mixed_levels = '')
            """)
        else:
            conn.execute(
                "UPDATE players SET player_name=?, license_id=?, club=?, gender=?, email=?, phone=?, dob=?, age=?, ranking=?, singles_levels=?, doubles_levels=?, mixed_levels=?, doubles_partner=?, mixed_partner=? WHERE player_id=?",
                (player["player_name"], player.get("license_id", ""), player["club"], player["gender"],
                 player.get("email", ""), player.get("phone", ""), player.get("dob", ""), player.get("age", ""), player.get("ranking", ""),
                 player.get("singles_levels", ""), player.get("doubles_levels", ""),
                 player.get("mixed_levels", ""), player.get("doubles_partner", ""),
                 player.get("mixed_partner", ""), player_id)
            )
    else:
        cur = conn.execute(
            "INSERT INTO players (player_name, license_id, club, gender, email, phone, dob, age, ranking, singles_levels, doubles_levels, mixed_levels, doubles_partner, mixed_partner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (player["player_name"], player.get("license_id", ""), player["club"], player["gender"],
             player.get("email", ""), player.get("phone", ""), player.get("dob", ""), player.get("age", ""), player.get("ranking", ""),
             player.get("singles_levels", ""), player.get("doubles_levels", ""),
             player.get("mixed_levels", ""), player.get("doubles_partner", ""),
             player.get("mixed_partner", ""))
        )
        player_id = cur.lastrowid

    # Auto-create mirrored entry for doubles partner
    doubles_partner = player.get("doubles_partner", "").strip()
    if doubles_partner:
        existing = conn.execute(
            "SELECT player_id FROM players WHERE player_name=? AND doubles_partner=?",
            (doubles_partner, player["player_name"])
        ).fetchone()
        if not existing:
            partner_club = get_player_club(doubles_partner)
            partner_license = get_player_license(doubles_partner)
            partner_ranking = get_player_ranking(doubles_partner)
            # Doubles partner has same gender
            partner_gender = player.get("gender", "")
            conn.execute(
                "INSERT INTO players (player_name, license_id, club, gender, ranking, singles_levels, doubles_levels, mixed_levels, doubles_partner, mixed_partner) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (doubles_partner, partner_license, partner_club, partner_gender, partner_ranking, "", player.get("doubles_levels", ""), "", player["player_name"], "")
            )

    # Auto-create mirrored entry for mixed partner
    mixed_partner = player.get("mixed_partner", "").strip()
    if mixed_partner:
        existing = conn.execute(
            "SELECT player_id FROM players WHERE player_name=? AND mixed_partner=?",
            (mixed_partner, player["player_name"])
        ).fetchone()
        if not existing:
            partner_club = get_player_club(mixed_partner)
            partner_license = get_player_license(mixed_partner)
            partner_ranking = get_player_ranking(mixed_partner)
            # Mixed partner has opposite gender
            player_gender = player.get("gender", "")
            partner_gender = "M" if player_gender == "F" else "F" if player_gender == "M" else ""
            conn.execute(
                "INSERT INTO players (player_name, license_id, club, gender, ranking, singles_levels, doubles_levels, mixed_levels, doubles_partner, mixed_partner) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (mixed_partner, partner_license, partner_club, partner_gender, partner_ranking, "", "", player.get("mixed_levels", ""), "", player["player_name"])
            )

    conn.commit()
    conn.close()
    return jsonify(success=True, player_id=player_id)


@app.route("/api/delete-player", methods=["POST"])
def delete_player():
    data = request.json
    db_file = data.get("dbFile")
    player_id = data.get("playerId")
    confirm = data.get("confirm", False)
    if not db_file or not player_id:
        return jsonify(success=False, error="Missing data"), 400
    conn = get_tournament_db(db_file)
    if not conn:
        return jsonify(success=False, error="Tournament not found"), 404

    # Get the player being deleted
    conn.row_factory = sqlite3.Row
    player = conn.execute("SELECT * FROM players WHERE player_id=?", (player_id,)).fetchone()
    if not player:
        conn.close()
        return jsonify(success=False, error="Player not found"), 404

    player_name = player["player_name"]

    # Find partners that reference this player
    partnerships = []
    auto_remove = []

    doubles_partners = conn.execute(
        "SELECT player_id, player_name, singles_levels, mixed_levels FROM players WHERE doubles_partner=?", (player_name,)
    ).fetchall()
    for p in doubles_partners:
        partnerships.append(f"{player_name} is playing doubles with {p['player_name']}")
        if not p["singles_levels"] and not p["mixed_levels"]:
            auto_remove.append(p["player_name"])

    mixed_partners = conn.execute(
        "SELECT player_id, player_name, singles_levels, doubles_levels FROM players WHERE mixed_partner=?", (player_name,)
    ).fetchall()
    for p in mixed_partners:
        partnerships.append(f"{player_name} is playing mixed with {p['player_name']}")
        if not p["singles_levels"] and not p["doubles_levels"]:
            auto_remove.append(p["player_name"])

    # If partnerships exist and not confirmed, return warning
    if partnerships and not confirm:
        if auto_remove:
            partnerships.append(f"\n{', '.join(auto_remove)} will also be removed (no remaining categories)")
        conn.close()
        return jsonify(success=False, needsConfirm=True, warnings=partnerships)

    # Delete the player
    conn.execute("DELETE FROM players WHERE player_id=?", (player_id,))

    # Clear partner references from other players
    conn.execute("UPDATE players SET doubles_partner='', doubles_levels='' WHERE doubles_partner=?", (player_name,))
    conn.execute("UPDATE players SET mixed_partner='', mixed_levels='' WHERE mixed_partner=?", (player_name,))

    # Remove players who now have no categories left
    conn.execute("""
        DELETE FROM players WHERE
            (singles_levels IS NULL OR singles_levels = '') AND
            (doubles_levels IS NULL OR doubles_levels = '') AND
            (mixed_levels IS NULL OR mixed_levels = '')
    """)

    conn.commit()
    conn.close()
    return jsonify(success=True)


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

            # Cache to local DB
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO players (name, profile_url, club, gender) VALUES (?, ?, ?, ?)",
                    (name, profile_url, club, None)
                )
            except sqlite3.Error:
                pass
        conn.commit()

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
                valid_categories = {"DS", "HS", "DD", "HD", "MD"}
                for row in table.find_all("tr")[1:]:
                    th = row.find("th", scope="row")
                    tds = row.find_all("td")
                    if th and len(tds) >= 2:
                        category = th.get_text(strip=True)
                        if category in valid_categories:
                            ranking[category] = {"rank": tds[0].get_text(strip=True), "points": tds[1].get_text(strip=True)}
        except Exception:
            pass

        return jsonify(success=True, gender=gender, email=email, phone=phone, ranking=ranking)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


def send_email(to_email, subject, body):
    """Send an email using configured SMTP settings."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    conn = sqlite3.connect(ADMIN_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM smtp_settings WHERE id=1")
    settings = cur.fetchone()
    conn.close()

    if not settings or not settings["smtp_email"] or not settings["smtp_password"]:
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = settings["smtp_email"]
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        port = settings["smtp_port"]
        host = settings["smtp_host"]

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()

        server.login(settings["smtp_email"], settings["smtp_password"])
        server.sendmail(settings["smtp_email"], to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[Email Error] {e}")
        return False


def send_reminders():
    """Check all tournaments and send reminders if registration closes within X days."""
    from datetime import datetime, timedelta

    conn = sqlite3.connect(ADMIN_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM smtp_settings WHERE id=1")
    settings = cur.fetchone()
    conn.close()

    if not settings or not settings["smtp_email"] or not settings["smtp_password"]:
        return

    reminder_days = settings["reminder_days"] or 3
    today = datetime.now().date()
    reminder_date = today + timedelta(days=reminder_days)

    if not os.path.exists(TOURNAMENTS_DIR):
        return

    for f in os.listdir(TOURNAMENTS_DIR):
        if not f.endswith(".db"):
            continue
        t_conn = get_tournament_db(f)
        if not t_conn:
            continue
        try:
            cur = t_conn.cursor()
            cur.execute("SELECT name, final_registration_date FROM tournaments LIMIT 1")
            row = cur.fetchone()
            if not row or not row[1]:
                t_conn.close()
                continue

            tournament_name = row[0]
            reg_close = datetime.strptime(row[1], "%Y-%m-%d").date()

            # Only send if registration closes within reminder_days
            if today <= reg_close <= reminder_date:
                # Get all players with email
                t_conn.row_factory = sqlite3.Row
                cur = t_conn.cursor()
                cur.execute("SELECT player_name, email FROM players WHERE email IS NOT NULL AND email != ''")
                players = cur.fetchall()

                admin_conn = sqlite3.connect(ADMIN_DB)
                for player in players:
                    # Check if reminder already sent
                    admin_cur = admin_conn.cursor()
                    admin_cur.execute(
                        "SELECT id FROM reminders_sent WHERE tournament_db=? AND player_email=?",
                        (f, player["email"])
                    )
                    if admin_cur.fetchone():
                        continue

                    # Send reminder
                    subject = f"Reminder: Registration closing soon for {tournament_name}"
                    body = (f"Hi {player['player_name']},\n\n"
                            f"This is a reminder that registration for '{tournament_name}' "
                            f"closes on {row[1]}.\n\n"
                            f"Please make sure your registration is complete.\n\n"
                            f"Best regards,\nBadminton Tournament System")

                    if send_email(player["email"], subject, body):
                        admin_conn.execute(
                            "INSERT INTO reminders_sent (tournament_db, player_email, sent_at) VALUES (?,?,?)",
                            (f, player["email"], datetime.now().isoformat())
                        )
                        print(f"[Reminder] Sent to {player['email']} for {tournament_name}")

                admin_conn.commit()
                admin_conn.close()
        except Exception as e:
            print(f"[Reminder Error] {f}: {e}")
        finally:
            t_conn.close()


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
