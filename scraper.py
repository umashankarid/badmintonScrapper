import time
import sqlite3
import string
import requests
from bs4 import BeautifulSoup

PLAYERS_DB = "players.db"
BASE_URL = "https://badmintonsweden.tournamentsoftware.com/find/player/DoSearch"

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}


def init_db():
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
    return conn


def scrape_page(conn, query, page=1):
    params = {"Page": page, "SportID": 2, "Query": query}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Error fetching {query} page {page}: {e}")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("li.list__item")
    count = 0

    for item in items:
        name_el = item.select_one("a.media__link span.nav-link__value")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        profile_link = item.select_one("a.media__link")
        profile_url = profile_link.get("href", "") if profile_link else ""
        club = ""
        club_el = item.select_one(".media__subheading span.nav-link__value")
        if club_el:
            club = club_el.get_text(strip=True).split("|")[0].strip()

        try:
            conn.execute(
                "INSERT OR IGNORE INTO players (name, profile_url, club, gender) VALUES (?, ?, ?, ?)",
                (name, profile_url, club, None)
            )
            count += 1
            print(f"  Saved: {name} - {club}")
        except sqlite3.Error as e:
            print(f"  DB error for {name}: {e}")

    conn.commit()
    return count


def run_scraper():
    conn = init_db()
    letters = string.ascii_lowercase

    for i in letters:
        for j in letters:
            for k in letters:
                query = f"{i}{j}{k}"
                print(f"Searching: {query}")
                scrape_page(conn, query)
                time.sleep(0.8)

    conn.close()
    print("Scraping finished.")


if __name__ == "__main__":
    run_scraper()
