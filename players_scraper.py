"""
Players Scraper Module
Scrapes player data from Badminton Sweden and updates players.db

Functions:
- scrape_player_by_license_id(license_id) - Scrape single player (run on login)
- check_player_data_stale(license_id) - Check if player data needs refresh
- get_player_by_license_id(license_id) - Get player data from local DB
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"
SEARCH_URL = f"{BASE_URL}/find/player/DoSearch"
PLAYERS_DB = "players.db"

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
