"""
bwf_submit.py — Playwright-based automation to submit tournament registrations
to Badminton Sweden (badmintonsweden.tournamentsoftware.com) using a club account.

Confirmed flow (tested and working):
  1. Accept cookie wall ("JAG GODKÄNNER")
  2. Login with club credentials (sbf04959)
  3. Navigate to /onlineentry/onlineentry.aspx?id={tournament_id}
  4. Click "Online-anmälan som grupp" (group entry)
  5. Check "Jag godkänner" + click "Nästa"
  6. Fill Team Manager: Andi Tandaputra, Tavlingar@bmkkomet.se, 0732103066
  7. Click "Nästa" to go to player composition page
  8. For each player/event: click "Lägg till spelare" → select from UL list → "Lägg till>>" → "Ok"
  9. For each doubles pair: click "Lägg till dubbel" → select both players → "Lägg till>>" → "Ok"
  10. Click "Spara" to submit all registrations
"""

import logging
import json
import re
import sqlite3
import os
from typing import Optional

logger = logging.getLogger(__name__)

TOURNAMENTS_DB = os.path.join(os.path.dirname(__file__), "tournaments.db")
PLAYERS_DB = os.path.join(os.path.dirname(__file__), "players.db")

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"

# Team Manager details (hardcoded for BMK Komet)
TEAM_MANAGER = {
    "first_name": "Andi",
    "last_name": "Tandaputra",
    "email": "Tavlingar@bmkkomet.se",
    "phone": "0732103066",
}


def get_tournament_registrations(tournament_name: str) -> list[dict]:
    """Get all registered players for a tournament with their event selections."""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute(f"ATTACH DATABASE '{PLAYERS_DB}' AS players_db")
        cur = conn.cursor()

        cur.execute("""
            SELECT p.name, r.license_id, p.club, p.gender,
                   r.singles_levels, r.doubles_levels, r.mixed_levels,
                   r.doubles_partner, r.mixed_partner
            FROM tournament_registrations r
            JOIN players_db.players p ON r.license_id = p.license_id
            WHERE r.tournament_name = ?
            ORDER BY p.name
        """, (tournament_name,))

        registrations = []
        for row in cur.fetchall():
            registrations.append({
                "player_name": row[0],
                "license_id": row[1],
                "club": row[2],
                "gender": row[3],
                "singles_levels": row[4] or "",
                "doubles_levels": row[5] or "",
                "mixed_levels": row[6] or "",
                "doubles_partner": row[7] or "",
                "mixed_partner": row[8] or "",
            })

        conn.close()
        return registrations
    except Exception as e:
        logger.error(f"Error fetching registrations: {e}")
        return []


def get_tournament_url(tournament_name: str) -> Optional[str]:
    """Get the BWF tournament URL for a tournament."""
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        cur.execute("SELECT tournament_url FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error fetching tournament URL: {e}")
        return None


def get_tournament_id_from_url(tournament_url: str) -> Optional[str]:
    """Extract the tournament UUID from the BWF URL."""
    match = re.search(r'/tournament/([A-Fa-f0-9-]+)', tournament_url)
    return match.group(1) if match else None


def _build_event_player_map(registrations: list[dict]) -> dict:
    """
    Build a mapping from event name → list of player names for singles,
    and event name → list of (player1, player2) tuples for doubles/mixed.
    
    This groups all registrations by event so we can add all players
    to each event in one popup interaction.
    """
    singles_map = {}  # event_name -> [player_name, ...]
    doubles_map = {}  # event_name -> [(player1_name, player2_name), ...]

    for reg in registrations:
        player_name = reg["player_name"]

        # Singles events
        if reg["singles_levels"]:
            for event in reg["singles_levels"].split(","):
                event = event.strip()
                if event:
                    if event not in singles_map:
                        singles_map[event] = []
                    singles_map[event].append(player_name)

        # Doubles events
        if reg["doubles_levels"]:
            partner = reg["doubles_partner"]
            for event in reg["doubles_levels"].split(","):
                event = event.strip()
                if event and partner:
                    if event not in doubles_map:
                        doubles_map[event] = []
                    pair = tuple(sorted([player_name, partner]))
                    if pair not in doubles_map[event]:
                        doubles_map[event].append(pair)

        # Mixed events
        if reg["mixed_levels"]:
            partner = reg["mixed_partner"]
            for event in reg["mixed_levels"].split(","):
                event = event.strip()
                if event and partner:
                    if event not in doubles_map:
                        doubles_map[event] = []
                    pair = tuple(sorted([player_name, partner]))
                    if pair not in doubles_map[event]:
                        doubles_map[event].append(pair)

    return {"singles": singles_map, "doubles": doubles_map}


async def submit_tournament_registrations(
    tournament_name: str,
    club_login: str,
    club_password: str,
    headless: bool = True,
    progress_callback=None
) -> dict:
    """
    Submit all tournament registrations to Badminton Sweden using Playwright.

    Args:
        tournament_name: Name of the tournament in our DB
        club_login: Club account login (e.g. 'sbf04959')
        club_password: Club account password
        headless: Whether to run browser in headless mode
        progress_callback: Optional callback function(message, current, total)

    Returns:
        dict with keys: success (bool), submitted (list), failed (list), message (str)
    """
    from playwright.async_api import async_playwright

    tournament_url = get_tournament_url(tournament_name)
    if not tournament_url:
        return {"success": False, "submitted": [], "failed": [],
                "message": f"Tournament URL not found for '{tournament_name}'"}

    tournament_id = get_tournament_id_from_url(tournament_url)
    if not tournament_id:
        return {"success": False, "submitted": [], "failed": [],
                "message": f"Could not extract tournament ID from URL: {tournament_url}"}

    registrations = get_tournament_registrations(tournament_name)
    if not registrations:
        return {"success": False, "submitted": [], "failed": [],
                "message": "No registrations found for this tournament"}

    # Build event → players mapping
    event_map = _build_event_player_map(registrations)
    total_singles = sum(len(players) for players in event_map["singles"].values())
    total_doubles = sum(len(pairs) for pairs in event_map["doubles"].values())
    total_ops = total_singles + total_doubles

    submitted = []
    failed = []

    def report(msg, current=0):
        logger.info(f"[BWF Submit] {msg}")
        if progress_callback:
            progress_callback(msg, current, total_ops)

    report(f"Starting: {len(registrations)} players, {total_singles} singles entries, {total_doubles} doubles entries")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # ===== STEP 1: Accept cookies + Login =====
            report("Logging in...")
            await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # Handle cookie wall
            cookie_btn = await page.query_selector('a:has-text("JAG GODKÄNNER"), button:has-text("JAG GODKÄNNER")')
            if cookie_btn:
                await cookie_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await page.wait_for_timeout(2000)

            # Navigate to login page (may need to re-navigate after cookie wall)
            if "cookiewall" in page.url:
                await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

            # Fill login form
            login_input = await page.query_selector('input[name="Login"]')
            if not login_input:
                await browser.close()
                return {"success": False, "submitted": [], "failed": [],
                        "message": "Could not load login page"}

            await page.fill('input[name="Login"]', club_login)
            await page.fill('input[name="Password"]', club_password)

            submit_btn = await page.query_selector('button[type="submit"]') or await page.query_selector('input[type="submit"]')
            if submit_btn:
                await submit_btn.click()
            else:
                await page.press('input[name="Password"]', 'Enter')

            await page.wait_for_load_state("networkidle", timeout=20000)

            # Verify login succeeded
            login_still = await page.query_selector('input[name="Login"]')
            if login_still:
                await browser.close()
                return {"success": False, "submitted": [], "failed": [],
                        "message": "Login failed - invalid credentials"}

            report("Login successful!")

            # ===== STEP 2: Navigate to online entry page =====
            report("Navigating to online entry page...")
            entry_url = f"{BASE_URL}/onlineentry/onlineentry.aspx?id={tournament_id}"
            await page.goto(entry_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # ===== STEP 3: Click "Online-anmälan som grupp" =====
            report("Clicking group entry...")
            group_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnGroupEntry')
            if not group_btn:
                await browser.close()
                return {"success": False, "submitted": [], "failed": [],
                        "message": "Could not find 'Online-anmälan som grupp' button. Registration may not be open."}
            await group_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)

            # ===== STEP 4: Accept terms + click Nästa =====
            report("Accepting terms...")
            agree_cb = await page.query_selector('#cphPage_cphPage_cphPage_VF1_fs0_agree')
            if agree_cb:
                if not await agree_cb.is_checked():
                    await agree_cb.check()
            else:
                # Try label click
                label = await page.query_selector('label[for="cphPage_cphPage_cphPage_VF1_fs0_agree"]')
                if label:
                    await label.click()

            next_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_0')
            if not next_btn:
                await browser.close()
                return {"success": False, "submitted": [], "failed": [],
                        "message": "Could not find 'Nästa' button after terms"}
            await next_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)

            # ===== STEP 5: Fill Team Manager =====
            report("Filling team manager...")
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerfirstname', TEAM_MANAGER["first_name"])
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerlastname', TEAM_MANAGER["last_name"])
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanageremail', TEAM_MANAGER["email"])
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerphone', TEAM_MANAGER["phone"])

            # Click Nästa to go to composition page
            next_btn2 = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_1')
            if not next_btn2:
                await browser.close()
                return {"success": False, "submitted": [], "failed": [],
                        "message": "Could not find 'Nästa' button after team manager"}
            await next_btn2.click()
            await page.wait_for_load_state("networkidle", timeout=15000)

            report("On player composition page!")

            # ===== STEP 6: Build event link mapping =====
            # Get all "Lägg till spelare" links and map them to event names
            singles_links = await _get_event_links(page, "Lägg till spelare")
            doubles_links = await _get_event_links(page, "Lägg till dubbel")

            report(f"Found {len(singles_links)} singles events, {len(doubles_links)} doubles events on page")

            # ===== STEP 7: Add singles players =====
            op_count = 0
            for event_name, players in event_map["singles"].items():
                if event_name not in singles_links:
                    for player in players:
                        failed.append({"player_name": player, "license_id": "",
                                       "error": f"Event '{event_name}' not found on BWF page"})
                    continue

                for player_name in players:
                    op_count += 1
                    report(f"Adding {player_name} to {event_name}...", op_count)
                    try:
                        success = await _add_singles_player(page, singles_links, event_name, player_name)
                        if success:
                            submitted.append({"player_name": player_name, "license_id": "",
                                              "message": f"Added to {event_name}"})
                        else:
                            failed.append({"player_name": player_name, "license_id": "",
                                           "error": f"Could not add to {event_name}"})
                    except Exception as e:
                        failed.append({"player_name": player_name, "license_id": "",
                                       "error": f"{event_name}: {str(e)}"})

            # ===== STEP 8: Add doubles/mixed pairs =====
            for event_name, pairs in event_map["doubles"].items():
                if event_name not in doubles_links:
                    for pair in pairs:
                        failed.append({"player_name": f"{pair[0]} & {pair[1]}", "license_id": "",
                                       "error": f"Event '{event_name}' not found on BWF page"})
                    continue

                for pair in pairs:
                    op_count += 1
                    pair_name = f"{pair[0]} & {pair[1]}"
                    report(f"Adding {pair_name} to {event_name}...", op_count)
                    try:
                        success = await _add_doubles_pair(page, doubles_links, event_name, pair[0], pair[1])
                        if success:
                            submitted.append({"player_name": pair_name, "license_id": "",
                                              "message": f"Added to {event_name}"})
                        else:
                            failed.append({"player_name": pair_name, "license_id": "",
                                           "error": f"Could not add to {event_name}"})
                    except Exception as e:
                        failed.append({"player_name": pair_name, "license_id": "",
                                       "error": f"{event_name}: {str(e)}"})

            # ===== STEP 9: Click "Spara" to submit =====
            report("Saving registration...")
            save_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnSubmit_2')
            if not save_btn:
                save_btn = await page.query_selector('input[value="Spara"]')
            if save_btn:
                await save_btn.click()
                await page.wait_for_timeout(10000)

                # Check for success message
                body_text = await page.inner_text("body")
                if "Tack" in body_text or "slutfört" in body_text:
                    report("✅ Registration saved successfully!")
                else:
                    report("⚠️ Save clicked but no confirmation message detected")
            else:
                failed.append({"player_name": "ALL", "license_id": "",
                               "error": "Could not find 'Spara' button"})

        except Exception as e:
            logger.error(f"[BWF Submit] Fatal error: {e}")
            return {
                "success": False,
                "submitted": submitted,
                "failed": failed,
                "message": f"Fatal error: {str(e)}"
            }
        finally:
            await browser.close()

    success = len(failed) == 0
    message = f"Submitted {len(submitted)} entries."
    if failed:
        message += f" {len(failed)} failed."

    return {
        "success": success,
        "submitted": submitted,
        "failed": failed,
        "message": message
    }


async def _get_event_links(page, link_text: str) -> dict:
    """
    Get mapping of event name → link index for "Lägg till spelare" or "Lägg till dubbel" links.
    
    The page structure has event names (e.g. "HS U11") in cells, followed by the add link.
    We extract the event name from the preceding table row/cell content.
    
    Returns dict: {"HS U11": 0, "HS U11 nivå 2": 1, "DS U11": 2, ...}
    """
    result = await page.evaluate("""
        (linkText) => {
            const links = document.querySelectorAll('a');
            const mapping = {};
            let index = 0;
            
            for (const link of links) {
                if (link.textContent.trim() === linkText) {
                    // Find the event name - it's in the preceding row or cell
                    // The structure is: <tr><td>EVENT NAME</td></tr><tr>...<a>Lägg till...</a></tr>
                    const row = link.closest('tr');
                    if (row) {
                        // Look at the previous sibling row for the event name
                        let prevRow = row.previousElementSibling;
                        while (prevRow) {
                            const text = prevRow.textContent.trim();
                            // Event names are like "HS U11", "DS U13 nivå 2", "MD U15"
                            if (text && !text.includes('Lägg till') && !text.includes('Starter') && !text.includes('position')) {
                                // Clean up - get just the event name
                                const eventName = text.split('\\n')[0].trim();
                                if (eventName && eventName.length < 30) {
                                    mapping[eventName] = index;
                                    break;
                                }
                            }
                            prevRow = prevRow.previousElementSibling;
                        }
                    }
                    index++;
                }
            }
            return mapping;
        }
    """, link_text)
    
    logger.info(f"Event links for '{link_text}': {result}")
    return result


async def _add_singles_player(page, event_links: dict, event_name: str, player_name: str) -> bool:
    """
    Add a single player to a singles event.
    
    Steps:
    1. Click the "Lägg till spelare" link for this event
    2. Find player in #ULAvailablePersons popup
    3. Click player <li> to select
    4. Click "Lägg till>>" to move to selected
    5. Click "Ok" to confirm
    """
    link_index = event_links.get(event_name)
    if link_index is None:
        logger.warning(f"Event '{event_name}' not found in link mapping")
        return False

    # Click the correct "Lägg till spelare" link
    links = await page.query_selector_all('a:has-text("Lägg till spelare")')
    if link_index >= len(links):
        logger.warning(f"Link index {link_index} out of range (have {len(links)} links)")
        return False

    await links[link_index].click()
    await page.wait_for_timeout(2000)

    # Find and click the player in the popup list
    # Player names in the list look like: "Kavin Ananda Sentraya Perumal (M, IID05891775)"
    # We search by first part of the name
    player_first = player_name.split()[0]
    kavin_li = await page.query_selector(f'#ULAvailablePersons li:has-text("{player_first}")')
    
    if not kavin_li:
        # Try full name
        kavin_li = await page.query_selector(f'#ULAvailablePersons li:has-text("{player_name}")')
    
    if not kavin_li:
        # Try with last name
        player_last = player_name.split()[-1]
        kavin_li = await page.query_selector(f'#ULAvailablePersons li:has-text("{player_last}")')

    if not kavin_li:
        logger.warning(f"Player '{player_name}' not found in available players list for {event_name}")
        await _close_dialog(page)
        return False

    # Click to select the player
    await kavin_li.click()
    await page.wait_for_timeout(500)

    # Click "Lägg till>>"
    add_clicked = await page.evaluate("""
        () => {
            const btn = document.getElementById('cphPage_cphPage_cphPage_btnAddPersonToSelection');
            if (btn) { btn.click(); return true; }
            return false;
        }
    """)
    if not add_clicked:
        logger.warning("Could not click 'Lägg till>>'")
        await _close_dialog(page)
        return False

    await page.wait_for_timeout(1500)

    # Click "Ok" to close popup
    ok_clicked = await _click_dialog_ok(page)
    if not ok_clicked:
        logger.warning("Could not click 'Ok'")
        await _close_dialog(page)
        return False

    await page.wait_for_timeout(2000)
    return True


async def _add_doubles_pair(page, event_links: dict, event_name: str, player1: str, player2: str) -> bool:
    """
    Add a doubles/mixed pair to an event.
    
    The doubles popup has:
    - Player 1 list: <ul id="ULPair1"> (club players only)
    - Player 2 list: <ul id="ULPair2"> (all players from all clubs + "<Partner önskas>")
    - Selected pairs section
    
    Steps:
    1. Click the "Lägg till dubbel" link for this event
    2. Select player1 from #ULPair1
    3. Select player2 from #ULPair2
    4. Click "Lägg till>>" (btnAddPairToSelection)
    5. Click "Ok" to confirm
    """
    link_index = event_links.get(event_name)
    if link_index is None:
        logger.warning(f"Event '{event_name}' not found in doubles link mapping")
        return False

    # Click the correct "Lägg till dubbel" link
    links = await page.query_selector_all('a:has-text("Lägg till dubbel")')
    if link_index >= len(links):
        logger.warning(f"Link index {link_index} out of range (have {len(links)} links)")
        return False

    await links[link_index].click()
    await page.wait_for_timeout(2000)

    # Select player 1 from #ULPair1 (club members)
    player1_first = player1.split()[0]
    player1_li = await page.query_selector(f'#ULPair1 li:has-text("{player1_first}")')
    if not player1_li:
        player1_last = player1.split()[-1]
        player1_li = await page.query_selector(f'#ULPair1 li:has-text("{player1_last}")')
    if not player1_li:
        logger.warning(f"Player 1 '{player1}' not found in #ULPair1 for {event_name}")
        await _close_dialog(page)
        return False

    await player1_li.click()
    await page.wait_for_timeout(500)

    # Select player 2 from #ULPair2 (all players)
    player2_first = player2.split()[0]
    player2_li = await page.query_selector(f'#ULPair2 li:has-text("{player2_first}")')
    if not player2_li:
        player2_last = player2.split()[-1]
        player2_li = await page.query_selector(f'#ULPair2 li:has-text("{player2_last}")')
    if not player2_li:
        logger.warning(f"Player 2 '{player2}' not found in #ULPair2 for {event_name}")
        await _close_dialog(page)
        return False

    await player2_li.click()
    await page.wait_for_timeout(500)

    # Click "Lägg till>>" for the pair
    add_clicked = await page.evaluate("""
        () => {
            const btn = document.getElementById('cphPage_cphPage_cphPage_btnAddPairToSelection');
            if (btn) { btn.click(); return true; }
            return false;
        }
    """)
    if not add_clicked:
        logger.warning("Could not click 'Lägg till>>' for doubles")
        await _close_dialog(page)
        return False

    await page.wait_for_timeout(1500)

    # Click "Ok"
    ok_clicked = await _click_dialog_ok(page)
    if not ok_clicked:
        logger.warning("Could not click 'Ok' for doubles")
        await _close_dialog(page)
        return False

    await page.wait_for_timeout(2000)
    return True


async def _close_dialog(page):
    """Close/cancel the current dialog."""
    await page.evaluate("""
        () => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                if ((a.textContent.trim() === 'Avbryt' || a.textContent.trim() === 'Close') 
                    && a.offsetParent !== null) {
                    a.click(); return;
                }
            }
        }
    """)
    await page.wait_for_timeout(1000)


async def _click_dialog_ok(page) -> bool:
    """Click the Ok button in the current dialog."""
    return await page.evaluate("""
        () => {
            const links = document.querySelectorAll('.ui-dialog a, .ui-dialog-buttonset button');
            for (const el of links) {
                if (el.textContent.trim() === 'Ok' || el.textContent.trim() === 'OK') {
                    el.click(); return true;
                }
            }
            const allLinks = document.querySelectorAll('a');
            for (const a of allLinks) {
                if (a.textContent.trim() === 'Ok' && a.offsetParent !== null) {
                    a.click(); return true;
                }
            }
            return false;
        }
    """)


def submit_tournament_sync(
    tournament_name: str,
    club_login: str,
    club_password: str,
    headless: bool = True,
    progress_callback=None
) -> dict:
    """
    Synchronous wrapper for submit_tournament_registrations.
    Use this from Flask routes.
    """
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            submit_tournament_registrations(
                tournament_name=tournament_name,
                club_login=club_login,
                club_password=club_password,
                headless=headless,
                progress_callback=progress_callback
            )
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in submit_tournament_sync: {e}")
        return {
            "success": False,
            "submitted": [],
            "failed": [],
            "message": f"Error: {str(e)}"
        }
