"""
Players Scraper Module
Scrapes player data from Badminton Sweden and updates players.db

Functions:
- scrape_all_players() - Bulk scrape all players (run on startup)
- scrape_player_by_license_id(license_id) - Scrape single player (run on login)
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


def scrape_all_players():
    """
    Bulk scrape all players from Badminton Sweden on startup.
    
    This completely replaces the players table with fresh data.
    - Deletes all existing players
    - Fetches all players from Badminton Sweden (A-Z search)
    - Populates players table with complete data
    """
    logger.info("🔄 Starting fresh bulk scrape of ALL players from Badminton Sweden")
    
    try:
        # STEP 1: Clear existing players table to start fresh
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM players")
        conn.commit()
        logger.info("🧹 Cleared players table for fresh data")
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️  Could not clear players table: {e}")
    
    try:
        players_found = 0
        players_failed = 0
        
        # Try searching common letters and combinations
        search_terms = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        
        for letter in search_terms:
            try:
                logger.debug(f"Searching for players starting with: {letter}")
                
                # Iterate through all pages for this letter
                page = 1
                while True:
                    # Use GET request with params (not POST)
                    resp = requests.get(
                        SEARCH_URL,
                        params={"Page": page, "SportID": 2, "Query": letter},
                        headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
                        timeout=10
                    )
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.select("li.list__item")
                    
                    if not items:
                        # No more pages for this letter
                        logger.debug(f"  Letter '{letter}': Complete (pages 1-{page-1})")
                        break
                    
                    logger.debug(f"  Letter '{letter}', Page {page}: {len(items)} items")
                    
                    for item in items:
                        try:
                            name_el = item.select_one("a.media__link span.nav-link__value")
                            license_el = item.select_one(".media__title-aside")
                            
                            if name_el and license_el:
                                name = name_el.get_text(strip=True)
                                license_id = license_el.get_text(strip=True).strip("()")
                                
                                profile_url = item.select_one("a.media__link")
                                profile_path = profile_url.get("href") if profile_url else ""
                                
                                # Only add valid entries (not temp_*, has name and license)
                                if name and not name.startswith("temp_") and license_id and not license_id.startswith("temp_"):
                                    if update_player_in_db(
                                        license_id=license_id,
                                        name=name,
                                        profile_url=profile_path
                                    ):
                                        players_found += 1
                                    else:
                                        players_failed += 1
                                    
                                    if players_found % 50 == 0:
                                        logger.info(f"🔍 Scraped {players_found} players so far...")
                        
                        except Exception as e:
                            logger.debug(f"Error processing item: {e}")
                            players_failed += 1
                            continue
                    
                    page += 1
            
            except Exception as e:
                logger.warning(f"⚠️  Error searching for '{letter}': {e}")
                continue
        
        logger.info(f"✅ Bulk scrape complete: {players_found} players added, {players_failed} failed")
        return players_found
    
    except Exception as e:
        logger.error(f"❌ Error in bulk scrape: {e}")
        return 0


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


def update_player_in_db(license_id, name, profile_url, ranking=None, email=None, phone=None):
    """
    Insert player in players.db (insert all entries, no deduplication)
    """
    try:
        conn = sqlite3.connect(PLAYERS_DB)
        cur = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Simple INSERT - store all 5,200 entries without deduplication
        cur.execute("""
            INSERT INTO players
            (license_id, name, profile_url, ranking, email, phone, last_updated, last_scraped)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (license_id, name, profile_url, ranking, email, phone, now, now))
        
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        logger.error(f"❌ Error inserting player in DB: {e}")
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
    print("\nNote: Bulk scrape takes a long time. Use sparingly!")
    # scrape_all_players()
