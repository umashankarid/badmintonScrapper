"""
Players Scraper Module
Scrapes player data from Badminton Sweden and updates players.db

Functions:
- scrape_player_by_license_id(license_id) - Scrape single player (run on login)
- check_player_data_stale(license_id) - Check if player data needs refresh
- get_player_by_license_id(license_id) - Get player data from local DB
"""

import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"
SEARCH_URL = f"{BASE_URL}/find/player/DoSearch"
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
PLAYERS_DB = os.path.join(DATA_DIR, "players.db")

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}


def scrape_player_by_license_id(license_id):
    """
    Scrape player data from Badminton Sweden by license ID
    Updates players.db with the scraped data
    
    Returns: dict with player data or None if not found
    """
    try:
        logger.info(f"🔍 Scraping player by license_id: {license_id}")
        
        # Fetch player profile page
        profile_url = f"{BASE_URL}/player-profile/{license_id}"
        resp = requests.get(profile_url, headers=HEADERS, timeout=10)
        
        if resp.status_code != 200:
            logger.warning(f"⚠️  Player not found: {license_id}")
            return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract player info
        player_data = {
            "license_id": license_id,
            "profile_url": f"/player-profile/{license_id}",
            "scraped_at": datetime.now().isoformat()
        }
        
        # Get player name
        name_elem = soup.select_one("h1.view__title")
        if name_elem:
            player_data["name"] = name_elem.get_text(strip=True)
        
        # Get club
        club_elem = soup.select_one(".row span")
        if club_elem:
            player_data["club"] = club_elem.get_text(strip=True)
        
        # Get gender from profile (if available)
        # Usually indicated by icon or text
        player_data["gender"] = ""
        
        # Scrape ranking
        ranking = {}
        try:
            ranking_resp = requests.get(f"{profile_url}/ranking", headers=HEADERS, timeout=10)
            ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
            ranking = scrape_ranking_from_page(ranking_soup)
            player_data["ranking"] = json.dumps(ranking)
        except Exception as e:
            logger.warning(f"⚠️  Could not scrape ranking: {e}")
            player_data["ranking"] = None
        
        logger.info(f"✅ Scraped player: {player_data.get('name', 'Unknown')}")
        
        # Update players.db with scraped data
        try:
            update_player_in_db(
                license_id=player_data.get("license_id"),
                name=player_data.get("name"),
                profile_url=player_data.get("profile_url"),
                ranking=player_data.get("ranking")
            )
            logger.info(f"✅ Updated players.db with {player_data.get('name', 'Unknown')}")
        except Exception as e:
            logger.error(f"❌ Could not update players.db: {e}")
        
        return player_data
    
    except Exception as e:
        logger.error(f"❌ Error scraping player {license_id}: {e}")
        return None


def scrape_ranking_from_page(soup):
    """
    Extract ranking data from Badminton Sweden ranking page
    
    Returns: dict in format
    {
        "singles": {
            "A": {"rank": 5, "points": 1250},
            ...
        },
        "doubles": {...}
    }
    """
    ranking = {
        "singles": {},
        "doubles": {},
        "mixed": {}
    }
    
    try:
        table = soup.find("table")
        if not table:
            return ranking
        
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            
            category = cells[0].get_text(strip=True)  # e.g., "A", "B", "HS", "DD"
            rank_text = cells[1].get_text(strip=True)
            points_text = cells[2].get_text(strip=True)
            
            rank = int(rank_text) if rank_text.isdigit() else None
            points = int(points_text) if points_text.isdigit() else 0
            
            # Categorize by type
            if category in ["HS", "A", "B", "C", "D", "Elit"]:
                # Singles category
                ranking["singles"][category] = {"rank": rank, "points": points}
            elif category in ["HD", "DD", "MD"]:
                # Doubles category
                ranking["doubles"][category] = {"rank": rank, "points": points}
    
    except Exception as e:
        logger.warning(f"⚠️  Error parsing ranking table: {e}")
    
    return ranking





def check_player_data_stale(license_id, max_age_hours=24):
    """
    Check if player data is stale (older than max_age_hours)
    
    Returns: True if stale or not found, False if current
    """
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT last_updated FROM players WHERE license_id = ?",
            (license_id,)
        )
        row = cur.fetchone()
        conn.close()
        
        if not row or not row[0]:
            # Player not found or no last_updated timestamp
            return True
        
        # Check if data is older than max_age_hours
        from datetime import datetime, timedelta
        last_updated = datetime.fromisoformat(row[0])
        age = datetime.now() - last_updated
        
        is_stale = age > timedelta(hours=max_age_hours)
        logger.debug(f"Player {license_id} data age: {age.total_seconds() / 3600:.1f} hours, stale={is_stale}")
        
        return is_stale
    
    except Exception as e:
        logger.warning(f"⚠️  Could not check player data freshness: {e}")
        return True  # Assume stale if we can't check


def update_player_in_db(license_id, name, profile_url, club=None, gender=None, email=None, phone=None, dob=None, age=None, ranking=None):
    """
    Insert or update player in players.db with all available fields.
    Uses license_id to detect existing player and update instead of duplicating.
    """
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Check if player already exists by license_id
        cur.execute("SELECT id FROM players WHERE license_id = ?", (license_id,))
        existing = cur.fetchone()
        
        if existing:
            # Update existing player - only update non-None fields
            cur.execute("""
                UPDATE players SET
                    name = COALESCE(?, name),
                    profile_url = COALESCE(?, profile_url),
                    club = COALESCE(?, club),
                    gender = COALESCE(?, gender),
                    email = COALESCE(?, email),
                    phone = COALESCE(?, phone),
                    dob = COALESCE(?, dob),
                    age = COALESCE(?, age),
                    ranking = COALESCE(?, ranking),
                    last_updated = ?,
                    last_scraped = ?
                WHERE license_id = ?
            """, (name, profile_url, club, gender, email, phone, dob, age, ranking, now, now, license_id))
        else:
            # Insert new player with all fields
            cur.execute("""
                INSERT INTO players
                (license_id, name, profile_url, club, gender, email, phone, dob, age, ranking, last_updated, last_scraped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (license_id, name, profile_url, club, gender, email, phone, dob, age, ranking, now, now))
        
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        logger.error(f"❌ Error inserting/updating player in DB: {e}")
        return False


def get_player_by_license_id(license_id):
    """
    Get player data from players.db
    """
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT license_id, name, profile_url, club, gender, email, phone, 
                   dob, age, ranking, last_updated
            FROM players WHERE license_id=?
        """, (license_id,))
        
        row = cur.fetchone()
        conn.close()
        
        if row:
            return {
                "license_id": row[0],
                "name": row[1],
                "profile_url": row[2],
                "club": row[3],
                "gender": row[4],
                "email": row[5],
                "phone": row[6],
                "dob": row[7],
                "age": row[8],
                "ranking": row[9],
                "last_updated": row[10]
            }
        return None
    
    except Exception as e:
        logger.error(f"❌ Error getting player from DB: {e}")
        return None


if __name__ == "__main__":
    # Test functions
    logging.basicConfig(level=logging.INFO)
    
    print("Testing players_scraper module...")
    print("\nUse scrape_player_by_license_id(license_id) to scrape individual players.")


# ==================== ALL PLAYERS BACKGROUND SCRAPER ====================

def init_allplayers_table():
    """Create the allplayers table in players.db if it doesn't exist"""
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS allplayers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT UNIQUE,
                name TEXT NOT NULL,
                profile_url TEXT,
                club TEXT,
                gender TEXT,
                last_scraped TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("✅ allplayers table initialized")
    except Exception as e:
        logger.error(f"❌ Error creating allplayers table: {e}")


def scrape_all_players_background():
    """
    Background scraper: fetches ALL players from Badminton Sweden A-Z with pagination.
    Stores in allplayers table. Deduplicates by license_id using a visited set.
    Runs in a background thread — does not block the app startup.
    """
    import time
    
    logger.info("=" * 60)
    logger.info("🔄 BACKGROUND: Starting full player scrape from Badminton Sweden...")
    logger.info("=" * 60)
    
    # Initialize table
    init_allplayers_table()
    
    # Load already-visited license_ids from DB to avoid re-processing on restart
    visited_license_ids = set()
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("SELECT license_id FROM allplayers WHERE license_id IS NOT NULL")
        visited_license_ids = {row[0] for row in cur.fetchall()}
        conn.close()
        logger.info(f"📋 Already have {len(visited_license_ids)} players in allplayers table")
    except Exception as e:
        logger.warning(f"⚠️  Could not load existing license_ids: {e}")
    
    # Create session with cookies accepted
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
        s.post(f"{BASE_URL}/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=10)
    except Exception as e:
        logger.error(f"❌ BACKGROUND: Could not connect to Badminton Sweden: {e}")
        return
    
    search_letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ")
    total_added = 0
    total_skipped = 0
    
    for letter in search_letters:
        page = 1
        while True:
            try:
                resp = s.get(
                    SEARCH_URL,
                    params={"Page": page, "SportID": 2, "Query": letter},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=10
                )
                
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("li.list__item")
                
                if not items:
                    break  # No more pages for this letter
                
                batch_entries = []
                
                for item in items:
                    name_el = item.select_one("a.media__link span.nav-link__value")
                    license_el = item.select_one(".media__title-aside")
                    
                    if not name_el or not license_el:
                        continue
                    
                    name = name_el.get_text(strip=True)
                    license_id = license_el.get_text(strip=True).strip("()")
                    
                    if not name or not license_id:
                        continue
                    
                    # DEDUPLICATION: Skip if already visited
                    if license_id in visited_license_ids:
                        total_skipped += 1
                        continue
                    
                    # Mark as visited
                    visited_license_ids.add(license_id)
                    
                    # Get profile URL and club
                    profile_link = item.select_one("a.media__link")
                    profile_url = profile_link.get("href", "") if profile_link else ""
                    
                    club = ""
                    club_el = item.select_one(".media__subheading span.nav-link__value")
                    if club_el:
                        club = club_el.get_text(strip=True).split("|")[0].strip()
                    
                    batch_entries.append((license_id, name, profile_url, club))
                
                # Batch insert to DB
                if batch_entries:
                    try:
                        conn = sqlite3.connect(PLAYERS_DB)
                        now = datetime.now().isoformat()
                        conn.executemany("""
                            INSERT OR IGNORE INTO allplayers (license_id, name, profile_url, club, last_scraped)
                            VALUES (?, ?, ?, ?, ?)
                        """, [(lid, n, p, c, now) for lid, n, p, c in batch_entries])
                        conn.commit()
                        conn.close()
                        total_added += len(batch_entries)
                    except Exception as e:
                        logger.error(f"⚠️  DB error for letter '{letter}' page {page}: {e}")
                
                if total_added % 100 == 0 and total_added > 0:
                    logger.info(f"🔄 BACKGROUND: {total_added} players added, {total_skipped} skipped (letter: {letter}, page: {page})")
                
                page += 1
                time.sleep(0.5)  # Be nice to the server
                
            except Exception as e:
                logger.warning(f"⚠️  Error on letter '{letter}' page {page}: {e}")
                break  # Move to next letter on error
    
    logger.info("=" * 60)
    logger.info(f"✅ BACKGROUND SCRAPE COMPLETE: {total_added} new players added, {total_skipped} duplicates skipped")
    logger.info(f"📊 Total in allplayers table: {len(visited_license_ids)}")
    logger.info("=" * 60)
