"""
Real Badminton Sweden access.

Every function here was moved verbatim from app.py. This is the only module in
the project that names tournamentsoftware.com.
"""

import json
import logging

import requests as ext_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"


def get_player_license(player_name):
    """Look up a player's license ID from Badminton Sweden search."""
    try:
        resp = ext_requests.get(
            f"{BASE_URL}/find/player/DoSearch",
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
        s.post(f"{BASE_URL}/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

        # Search for the player to get their profile URL
        resp = s.get(
            f"{BASE_URL}/find/player/DoSearch",
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
            f"{BASE_URL}{profile_url}/ranking",
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


def _authenticate(username, password):
    """Accept the cookiewall, fetch the verification token, POST the credentials.

    Returns (session, soup) where soup is the parsed POST response. Shared by
    login() and verify_credentials(), which submit the identical sequence.
    """
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    # Accept cookies
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/user",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=10)

    # Get login page for verification token
    resp = s.get(f"{BASE_URL}/user", timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    token_el = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_el:
        raise RuntimeError("Could not load login page")

    # Submit login
    logo_el = soup.find("input", {"name": "LogoUrl"})
    resp = s.post(f"{BASE_URL}/user", data={
        "__RequestVerificationToken": token_el.get("value", ""),
        "ReturnUrl": "/",
        "LogoUrl": logo_el.get("value", "") if logo_el else "",
        "Login": username,
        "Password": password
    }, allow_redirects=True, timeout=10)

    return s, BeautifulSoup(resp.text, "html.parser")


def verify_credentials(username, password):
    """True when Badminton Sweden accepts these credentials."""
    _, soup = _authenticate(username, password)
    return soup.find("input", {"name": "Login"}) is None


def login(username, password):
    """Log in and scrape the player's profile. None means the login was rejected."""
    s, soup = _authenticate(username, password)

    # Check if login failed - still on login page
    login_input = soup.find("input", {"name": "Login"})
    if login_input:
        return None

    # After login, find the profile link in the nav ("Min profil" -> /player-profile/<UUID>)
    profile_url = ""
    profile_link = soup.select_one("a[href*='player-profile']")
    if not profile_link:
        # Try fetching homepage explicitly
        resp = s.get(f"{BASE_URL}/", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        profile_link = soup.select_one("a[href*='player-profile']")

    if profile_link:
        profile_url = profile_link.get("href", "")

    print(f"[BWF Login] Profile URL found: {profile_url}")

    if not profile_url:
        # Club account (no player profile) - check if it's a known admin account
        if username in ("sbf04959", "umashankar1985@gmail.com"):
            # Club/admin account - proceed without player profile
            player_name = username
            name_el = soup.select_one(".masthead__user-title")
            if name_el:
                player_name = name_el.get_text(strip=True)

            return {
                "player_name": player_name,
                "license_id": "",
                "club": "",
                "gender": "",
                "email": "",
                "phone": "",
                "dob": "",
                "age": "",
                "ranking": {},
                "profile_url": "",
                "is_club_account": True,
            }
        else:
            return None

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
            f"{BASE_URL}/find/player/DoSearch",
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
        settings_resp = s.get(f"{BASE_URL}/user/account-settings/person", timeout=10)
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
        ranking_resp = s.get(f"{BASE_URL}{profile_url}/ranking", timeout=10)
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
        player_name = username

    return {
        "player_name": player_name,
        "license_id": license_id,
        "club": club,
        "gender": gender,
        "email": email,
        "phone": phone,
        "dob": dob,
        "age": age,
        "ranking": ranking,
        "profile_url": profile_url,
        "is_club_account": False,
    }
