"""
Real Badminton Sweden access.

Every function here was moved verbatim from app.py. This is the only module in
the project that names tournamentsoftware.com.
"""

import json
import logging
import re

import requests as ext_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"

# The event-class prefixes app.py has always looked for on the events page.
EVENT_CATEGORIES = ["HS", "DS", "HD", "DD", "MD", "PS", "FS", "PD", "FD"]


class LoginPageUnavailable(Exception):
    """The login form could not be loaded, so no credentials were ever submitted."""


class ProfileNotFound(Exception):
    """The credentials were accepted but the account has no player profile."""


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
        raise LoginPageUnavailable("Could not load login page")

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
            raise ProfileNotFound("Login succeeded but could not find player profile")

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


def search_players(query):
    """Search Badminton Sweden for players matching query. Empty list on any failure."""
    try:
        resp = ext_requests.get(
            f"{BASE_URL}/find/player/DoSearch",
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
        return live_results
    except Exception:
        return []


def get_player_details(profile_url):
    """Fetch full player details (gender, email, phone, ranking) from Badminton Sweden profile."""
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    # Fetch player profile page to get gender
    gender = ""
    resp = s.get(f"{BASE_URL}{profile_url}", timeout=10)
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

    return {"gender": gender, "email": email, "phone": phone, "ranking": ranking}


def get_player_ranking_by_profile(profile_url):
    """Ranking for a known profile URL. Cookiewall + ranking page only.

    Moved verbatim from _register_partner's original inline ranking fetch
    (pre-Task-6) — deliberately not routed through get_player_details, which
    also fetches the profile page and would add a request and a new failure
    mode that did not exist before.
    """
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)
    ranking_resp = s.get(f"{BASE_URL}{profile_url}/ranking", timeout=10)
    ranking_soup = BeautifulSoup(ranking_resp.text, "html.parser")
    table = ranking_soup.find("table")
    ranking_data = {}
    if table:
        for row in table.find_all("tr")[1:]:
            th = row.find("th", scope="row")
            tds = row.find_all("td")
            if th and len(tds) >= 2:
                category = th.get_text(strip=True)
                if category:
                    ranking_data[category] = {"rank": tds[0].get_text(strip=True), "points": tds[1].get_text(strip=True)}
    return ranking_data


def get_tournament_events(tournament_id, session=None):
    """Event classes for one tournament, in the two shapes app.py derives from them.

    "levels" is the bare level of each class ("HS A" -> "A"), which
    /admin/fetch-tournament-info shows; the three *_levels lists are the full
    class names, which the registration form stores as categories.

    session is an already-cookiewalled session to reuse. fetch_tournament_info
    passes its own so that scraping a tournament costs the same three requests
    the inline code in app.py made, instead of a second cookiewall and a second
    events page.
    """
    if session is None:
        session = ext_requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        session.post(f"{BASE_URL}/cookiewall/Save", data={
            "ReturnUrl": "/",
            "SettingsOpen": "false",
            "CookieWallCategoryPreferences": "1,2,3"
        }, allow_redirects=True, timeout=5)

    events_resp = session.get(f"{BASE_URL}/sport/events.aspx?id={tournament_id}", timeout=10)
    events_soup = BeautifulSoup(events_resp.text, "html.parser")

    all_events = set()
    level_set = set()
    for a in events_soup.select("a"):
        text = a.get_text(strip=True)
        if text and len(text) < 50 and any(cat in text for cat in EVENT_CATEGORIES):
            all_events.add(text.strip())
            parts = text.split()
            if len(parts) >= 2:
                level_set.add(parts[1])

    events = {
        "singles_levels": [],
        "doubles_levels": [],
        "mixed_levels": [],
        "levels": sorted(level_set),
    }
    for event in sorted(all_events):
        if event.startswith(("HS", "DS")):
            events["singles_levels"].append(event)
        elif event.startswith(("HD", "DD")):
            events["doubles_levels"].append(event)
        elif event.startswith("MD"):
            events["mixed_levels"].append(event)
    return events


def _fetch_tournament(url, tolerate_missing_events):
    """One tournament page plus its events page: one cookiewall POST, two GETs.

    tolerate_missing_events is the one thing the two callers below disagree on,
    so it stays a parameter rather than being unified away.
    """
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
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

    # Get event classes from the events page, on the same session
    events = {"singles_levels": [], "doubles_levels": [], "mixed_levels": [], "levels": []}
    tid_match = re.search(r'/tournament/([^/]+)', url)
    if tid_match:
        try:
            events = get_tournament_events(tid_match.group(1), session=s)
        except Exception as e:
            if not tolerate_missing_events:
                raise
            logger.debug(f"⚠️  Could not extract categories: {e}")

    return {
        "name": name,
        "location": location,
        "levels": events["levels"],
        "singles_levels": events["singles_levels"],
        "doubles_levels": events["doubles_levels"],
        "mixed_levels": events["mixed_levels"],
        "registration_opens": dates.get("registration_opens", ""),
        "registration_closes": dates.get("registration_closes", ""),
        "cancellation_deadline": dates.get("cancellation_deadline", ""),
        "competition_start": dates.get("competition_start", ""),
        "competition_end": dates.get("competition_end", ""),
    }


def fetch_tournament_info(url):
    """Everything app.py reads off a tournament page. Every date is YYYY-MM-DD or "".

    A failing events page fails the whole call, which is what
    /admin/fetch-tournament-info has always done with it.
    """
    return _fetch_tournament(url, tolerate_missing_events=False)


def fetch_tournament_details(url):
    """The same scrape, but a failing events page only empties the event lists.

    ensure_tournament and the calendar refresh have always wrapped their events
    fetch in their own try/except and stored the tournament regardless; keeping
    that difference is cheaper than changing when they fail.
    """
    return _fetch_tournament(url, tolerate_missing_events=True)


def search_tournaments(start, end, status):
    """Tournaments in a date range, for the results page.

    start and end are "YYYY-MM-DD" or ""; status is the site's StatusFilterID
    ("2" registration open, "3" upcoming, "4" finished) or "" for no filter.
    Each result is {"id", "name", "location", "date_start", "date_end", "status"}.
    """
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    start_fmt = f"{start}T00:00" if start else ""
    end_fmt = f"{end}T00:00" if end else ""

    url = f"{BASE_URL}/find?DateFilterType=0&StartDate={start_fmt}&EndDate={end_fmt}&Distance=10&page=1&SportID=2"
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

    resp = s.post(f"{BASE_URL}/find/tournament/DoSearch",
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

    return tournaments


def list_all_tournaments(start_date, end_date):
    """Every tournament with registration open in a window, from the find page.

    start_date and end_date are the site's own "YYYY-MM-DDTHH:MM" format. Each
    result is {"name", "url", "location", "date_start", "date_end"}; the status
    filter is fixed at 2 ("Online-anmalan oppen"), as both callers always sent it.
    """
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    # Load the find page to get form data
    resp = s.get(f"{BASE_URL}/find?StatusFilterID=2&DateFilterType=0&StartDate={start_date}&EndDate={end_date}&Distance=10&page=1&SportID=2", timeout=10)
    page_soup = BeautifulSoup(resp.text, "html.parser")
    form = page_soup.select_one("#form_globalsearch")
    form_data = {}
    if form:
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            value = inp.get("value", "")
            if name:
                form_data[name] = value

    # Set StatusFilterID to 2 for 'Online-anmalan oppen' (registration open)
    form_data["TournamentExtendedFilter.StatusFilterID"] = "2"

    # POST to get results
    resp = s.post(f"{BASE_URL}/find/tournament/DoSearch",
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
        tid_match = re.search(r'id=([A-Fa-f0-9-]+)', href)
        tournament_url = f"{BASE_URL}/tournament/{tid_match.group(1)}" if tid_match else ""

        tournaments.append({
            "name": name,
            "url": tournament_url,
            "location": location,
            "date_start": date_start,
            "date_end": date_end
        })

    return tournaments


def get_tournament_medals(tournament_id):
    """Medal winners from a tournament's winners page."""
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    resp = s.get(f"{BASE_URL}/sport/winners.aspx?id={tournament_id}", timeout=15)
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

    return medals


def get_tournament_player_id(tournament_id, player_name):
    """A player's ID from the tournament player list, matched by name. "" when not found."""
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    resp = s.get(f"{BASE_URL}/tournament/{tournament_id}/Players/GetPlayersContent",
        headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True) == player_name or player_name in a.get_text(strip=True):
            href = a.get("href", "")
            match = re.search(r"player=(\d+)", href)
            if match:
                return match.group(1)

    return ""


def get_tournament_player_results(tournament_id, player_id):
    """A player's stats table and match history for one tournament."""
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/", "SettingsOpen": "false", "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    resp = s.get(f"{BASE_URL}/tournament/{tournament_id}/player/{player_id}", timeout=15)
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

    return {"stats": stats, "matches": matches}


def get_tournament_clubs(tournament_id):
    """Every player and club from a tournament's player list, deduplicated by name."""
    s = ext_requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    url = f"{BASE_URL}/tournament/{tournament_id}/Players/GetPlayersContent"
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

    return unique_players


def submit_registrations(tournament_name, club_login, club_password):
    """File the club's entries on Badminton Sweden. Launches a real browser."""
    from bwf_submit import submit_tournament_sync

    return submit_tournament_sync(
        tournament_name=tournament_name,
        club_login=club_login,
        club_password=club_password,
        headless=True,
    )
