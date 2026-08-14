"""
test_bwf_steps.py — Test the first BWF submission steps with Playwright.

Run with:
    python3 test_bwf_steps.py

This will:
1. Login as sbf04959
2. Navigate to tournament online entry page
3. Click "Online-anmälan som grupp"
4. Check "Jag godkänner" and click "Nästa"
5. Print what's on the next page (for debugging)

Usage:
    python3 test_bwf_steps.py <password>
"""

import asyncio
import sys

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"
TOURNAMENT_ID = "A2AB5259-7C92-4A4D-88C1-CC7A0C6DCD4F"  # Komet Hösttävling 2026
CLUB_LOGIN = "sbf04959"


async def test_steps(password: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        try:
            # ===== STEP 1: Login =====
            print("Step 1: Logging in...")
            
            # First accept cookies
            print("   Accepting cookies...")
            await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            
            # Handle cookie wall - click "JAG GODKÄNNER"
            cookie_accept = await page.query_selector('a:has-text("JAG GODKÄNNER"), button:has-text("JAG GODKÄNNER"), a:has-text("Jag godkänner")')
            if cookie_accept:
                print("   Found cookie wall, clicking 'JAG GODKÄNNER'...")
                await cookie_accept.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await page.wait_for_timeout(2000)
            else:
                # Try submitting the cookie form directly
                print("   Trying direct cookie form submission...")
                await page.goto(f"{BASE_URL}/cookiewall/Save?ReturnUrl=%2Fuser&SettingsOpen=false&CookieWallCategoryPreferences=1%2C2%2C3", wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
            
            # Now go to login page
            print("   Loading login page...")
            await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            
            # Debug: print what we see
            page_url = page.url
            print(f"   Current URL: {page_url}")
            content = await page.content()
            # Check if there's a cookie wall blocking
            if "cookiewall" in content.lower() or "cookie" in content.lower():
                print("   Cookie wall detected, trying to accept...")
                # Try clicking any visible accept/save button
                for sel in ['button:has-text("Save")', 'button:has-text("Spara")', 'input[type="submit"]', '#save-cookie-settings', 'button.cookie', 'a:has-text("Accept")']:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        print(f"   Clicking: {sel}")
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        break
                # Navigate to login again
                await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                page_url = page.url
                print(f"   After cookie accept, URL: {page_url}")
            
            # Wait for login form
            login_input = await page.query_selector('input[name="Login"]')
            if not login_input:
                print("   Login input not found, checking page...")
                # Save debug screenshot
                await page.screenshot(path="bwf_debug_login.png", full_page=True)
                print("   📸 Debug screenshot: bwf_debug_login.png")
                # Print first part of page
                body = await page.inner_text("body")
                print(f"   Page text (first 500 chars): {body[:500]}")
                await browser.close()
                return
            
            await page.fill('input[name="Login"]', CLUB_LOGIN)
            await page.fill('input[name="Password"]', password)
            
            # Find and click submit button
            submit_btn = await page.query_selector('button[type="submit"]') or await page.query_selector('input[type="submit"]')
            if submit_btn:
                await submit_btn.click()
            else:
                await page.press('input[name="Password"]', 'Enter')
            
            await page.wait_for_load_state("networkidle", timeout=20000)

            # Verify login
            login_input = await page.query_selector('input[name="Login"]')
            if login_input:
                print("❌ Step 1 FAILED: Still on login page (bad credentials?)")
                await browser.close()
                return
            print("✅ Step 1: Login successful!")

            # ===== STEP 2: Navigate to tournament page =====
            print("\nStep 2: Navigating to tournament page...")
            tournament_url = f"{BASE_URL}/tournament/{TOURNAMENT_ID}"
            await page.goto(tournament_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle", timeout=10000)
            print(f"✅ Step 2: On tournament page. Title: {await page.title()}")

            # ===== STEP 3: Navigate to online entry page =====
            print("\nStep 3: Navigating to online entry page...")
            entry_url = f"{BASE_URL}/onlineentry/onlineentry.aspx?id={TOURNAMENT_ID}"
            await page.goto(entry_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle", timeout=10000)
            print(f"✅ Step 3: On online entry page. Title: {await page.title()}")

            # ===== STEP 4: Click "Online-anmälan som grupp" =====
            print("\nStep 4: Clicking 'Online-anmälan som grupp'...")
            group_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnGroupEntry')
            if not group_btn:
                print("❌ Step 4 FAILED: Could not find 'Online-anmälan som grupp' button")
                # Print page content for debugging
                content = await page.content()
                print(f"   Page snippet: {content[:500]}")
                await browser.close()
                return
            await group_btn.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            print(f"✅ Step 4: Clicked group entry. Title: {await page.title()}")

            # ===== STEP 5: Check "Jag godkänner" and click "Nästa" =====
            print("\nStep 5: Accepting terms and clicking 'Nästa'...")
            
            # Check the "Jag godkänner" checkbox
            agree_checkbox = await page.query_selector('#cphPage_cphPage_cphPage_VF1_fs0_agree')
            if not agree_checkbox:
                # Try by label
                agree_label = await page.query_selector('label[for="cphPage_cphPage_cphPage_VF1_fs0_agree"]')
                if agree_label:
                    await agree_label.click()
                    print("   Clicked label for 'Jag godkänner'")
                else:
                    print("❌ Step 5 FAILED: Could not find 'Jag godkänner' checkbox")
                    content = await page.content()
                    print(f"   Page snippet: {content[:1000]}")
                    await browser.close()
                    return
            else:
                is_checked = await agree_checkbox.is_checked()
                if not is_checked:
                    await agree_checkbox.check()
                print("   Checked 'Jag godkänner'")

            # Click "Nästa"
            next_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_0')
            if not next_btn:
                print("❌ Step 5 FAILED: Could not find 'Nästa' button")
                content = await page.content()
                print(f"   Page snippet: {content[:1000]}")
                await browser.close()
                return
            await next_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            print(f"✅ Step 5: Clicked 'Nästa'. Title: {await page.title()}")

            # ===== PRINT NEXT PAGE FOR DEBUGGING =====
            print("\n" + "=" * 60)
            print("NEXT PAGE CONTENT (for debugging next steps):")
            print("=" * 60)
            
            # ===== STEP 6: Fill Team Manager fields =====
            print("\nStep 6: Filling Team Manager fields...")
            
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerfirstname', 'Andi')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerlastname', 'Tandaputra')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanageremail', 'Tavlingar@bmkkomet.se')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerphone', '0732103066')
            print("   ✅ Filled: Andi Tandaputra, Tavlingar@bmkkomet.se, 0732103066")
            
            # Click "Nästa" to go to next page
            print("   Clicking 'Nästa'...")
            next_btn2 = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_1')
            if not next_btn2:
                print("❌ Step 6 FAILED: Could not find 'Nästa' button")
                await page.screenshot(path="bwf_step6_error.png", full_page=True)
                await browser.close()
                return
            await next_btn2.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            print(f"✅ Step 6: Clicked 'Nästa'. Title: {await page.title()}")
            
            # ===== PRINT NEXT PAGE =====
            print("\n" + "=" * 60)
            print("PAGE AFTER TEAM MANAGER (Step 7):")
            print("=" * 60)
            
            # ===== STEP 7: Add player to HS U11 =====
            print("\nStep 7: Adding Kavin Ananda Sentraya Perumal to HS U11...")
            
            await page.wait_for_timeout(2000)
            
            # Click first "Lägg till spelare" (HS U11)
            add_links = await page.query_selector_all('a:has-text("Lägg till spelare")')
            print(f"   Found {len(add_links)} 'Lägg till spelare' links")
            
            if not add_links:
                print("❌ No 'Lägg till spelare' links found")
                await browser.close()
                return
            
            print("   Clicking first 'Lägg till spelare' (HS U11)...")
            await add_links[0].click()
            await page.wait_for_timeout(3000)
            
            # Popup is now open: "Välj spelare för HS U11"
            # It's a jQuery UI dialog with:
            # - Dialog: #cphPage_cphPage_cphPage_dlgSingle
            # - Available players: <ul id="ULAvailablePersons"> with <li> items
            # - Selected players: likely another <ul>
            # We need to:
            # 1. Click on Kavin's <li> in ULAvailablePersons to select him
            # 2. Click "Lägg till>>" to move to selected
            # 3. Click "Ok" to confirm
            
            # Find Kavin in the available players list
            print("   Looking for Kavin in #ULAvailablePersons...")
            kavin_li = await page.query_selector('#ULAvailablePersons li:has-text("Kavin")')
            if not kavin_li:
                # Try broader search
                kavin_li = await page.query_selector('ul#ULAvailablePersons li:has-text("Kavin")')
            if not kavin_li:
                kavin_li = await page.query_selector('li:has-text("Kavin")')
            
            if kavin_li:
                print("   Found Kavin <li> - clicking to select...")
                await kavin_li.click()
                await page.wait_for_timeout(1000)
            else:
                print("   ❌ Could not find Kavin in list")
                # Debug: print all li items
                lis = await page.query_selector_all('#ULAvailablePersons li')
                print(f"   LI items in ULAvailablePersons: {len(lis)}")
                for li in lis[:10]:
                    text = await li.inner_text()
                    print(f"     - {text[:80]}")
                await page.screenshot(path="bwf_step7_no_kavin.png", full_page=True)
                await browser.close()
                return
            
            # Click "Lägg till>>" button to move to selected
            print("   Clicking 'Lägg till>>'...")
            add_clicked = await page.evaluate("""
                () => {
                    const btn = document.getElementById('cphPage_cphPage_cphPage_btnAddPersonToSelection');
                    if (btn) { btn.click(); return true; }
                    // Fallback
                    const inputs = document.querySelectorAll('input[value="Lägg till>>"]');
                    for (const inp of inputs) { if (inp.offsetParent !== null) { inp.click(); return true; } }
                    return false;
                }
            """)
            if add_clicked:
                await page.wait_for_timeout(2000)
                print("   ✅ Clicked 'Lägg till>>'")
            else:
                print("   ❌ Could not find 'Lägg till>>' button")
                await browser.close()
                return
            
            # Click "Ok" to close popup and confirm
            print("   Clicking 'Ok'...")
            # Use JavaScript to find and click the Ok button in the dialog
            ok_clicked = await page.evaluate("""
                () => {
                    // Find the dialog buttons - jQuery UI dialogs have buttonpane
                    const buttons = document.querySelectorAll('.ui-dialog-buttonset button, .ui-dialog-buttonpane button, .ui-dialog a');
                    for (const btn of buttons) {
                        if (btn.textContent.trim() === 'Ok' || btn.textContent.trim() === 'OK') {
                            btn.click();
                            return true;
                        }
                    }
                    // Also try any visible anchor with "Ok" text
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        if (a.textContent.trim() === 'Ok' && a.offsetParent !== null) {
                            a.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if ok_clicked:
                await page.wait_for_timeout(3000)
                print("   ✅ Clicked 'Ok' via JS")
            else:
                print("   ❌ Could not find/click 'Ok' button via JS")
                await page.screenshot(path="bwf_step7_no_ok.png", full_page=True)
                await browser.close()
                return
            
            # Verify player was added
            body_text = await page.inner_text("body")
            if "Kavin" in body_text and "1 Starter" in body_text:
                print("   ✅ Kavin appears in registration! (1 Starter)")
            elif "Kavin" in body_text:
                print("   ✅ Kavin visible on page after adding")
            else:
                print("   ⚠️ Kavin not visible after adding - checking...")
            
            await page.screenshot(path="bwf_step7_after_add.png", full_page=True)
            print("   📸 Screenshot: bwf_step7_after_add.png")
            
            # ===== STEP 8: Save/Submit =====
            print("\nStep 8: Clicking 'Spara' to save...")
            
            # Check current page state
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text("body")
            if "Kavin" in body_text:
                print("   ✅ Kavin still visible on page")
            
            # Look for save button with various selectors
            save_selectors = [
                '#cphPage_cphPage_cphPage_btnSubmit_2',
                'input[value="Spara"]',
                'button:has-text("Spara")',
                '#cphPage_cphPage_cphPage_btnSubmit_1',
                'input[type="submit"][value="Spara"]',
                '#cphPage_cphPage_cphPage_btnNext_2',
            ]
            
            save_btn = None
            for sel in save_selectors:
                save_btn = await page.query_selector(sel)
                if save_btn:
                    is_visible = await save_btn.is_visible()
                    print(f"   Found button: {sel} (visible: {is_visible})")
                    if is_visible:
                        break
                    save_btn = None
            
            if not save_btn:
                print("   Looking for all submit/button elements...")
                all_buttons = await page.query_selector_all('input[type="submit"], button')
                for btn in all_buttons:
                    value = await btn.get_attribute("value") or ""
                    text = ""
                    try:
                        text = await btn.inner_text()
                    except:
                        pass
                    btn_id = await btn.get_attribute("id") or ""
                    is_visible = await btn.is_visible()
                    if is_visible and (value or text):
                        print(f"     Button: id='{btn_id}' value='{value}' text='{text}' visible={is_visible}")
                
                await page.screenshot(path="bwf_step8_no_save.png", full_page=True)
                print("   📸 Screenshot: bwf_step8_no_save.png")
            else:
                await save_btn.click()
                await page.wait_for_timeout(10000)  # Wait for save to complete
                print("✅ Step 8: Clicked 'Spara'!")
                await page.screenshot(path="bwf_step8_saved.png", full_page=True)
                print("   📸 Screenshot: bwf_step8_saved.png")
                
                # Print result page
                result_text = await page.inner_text("body")
                print(f"\n   Result page (first 500 chars):\n   {result_text[:500]}")
            
            await browser.close()
            return
            
            # Get page text content (stripped of HTML)
            body_text = await page.inner_text("body")
            # Print first 2000 chars
            print(body_text[:2000])
            
            print("\n" + "=" * 60)
            print("KEY FORM ELEMENTS ON NEXT PAGE:")
            print("=" * 60)
            
            # Find inputs
            inputs = await page.query_selector_all('input[type="text"], input[type="search"], select, textarea')
            for inp in inputs[:20]:
                tag = await inp.evaluate("el => el.tagName")
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                print(f"  <{tag}> name='{name}' id='{id_attr}' placeholder='{placeholder}'")
            
            # Find buttons
            buttons = await page.query_selector_all('input[type="submit"], button[type="submit"], a.nextbutton')
            for btn in buttons[:10]:
                tag = await btn.evaluate("el => el.tagName")
                text = await btn.inner_text() if tag == "BUTTON" or tag == "A" else await btn.get_attribute("value")
                id_attr = await btn.get_attribute("id") or ""
                print(f"  <{tag}> text='{text}' id='{id_attr}'")
            
            # Find checkboxes
            checkboxes = await page.query_selector_all('input[type="checkbox"]')
            for cb in checkboxes[:20]:
                name = await cb.get_attribute("name") or ""
                id_attr = await cb.get_attribute("id") or ""
                # Get associated label
                label_text = ""
                label = await page.query_selector(f'label[for="{id_attr}"]')
                if label:
                    label_text = await label.inner_text()
                print(f"  <CHECKBOX> name='{name}' id='{id_attr}' label='{label_text}'")

            # Take a screenshot for reference
            await page.screenshot(path="bwf_step5_next_page.png", full_page=True)
            print("\n📸 Screenshot saved to: bwf_step5_next_page.png")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            # Save screenshot on error
            try:
                await page.screenshot(path="bwf_error.png", full_page=True)
                print("📸 Error screenshot saved to: bwf_error.png")
            except:
                pass
        finally:
            await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_bwf_steps.py <club_password>")
        print("  This tests the first 5 BWF submission steps.")
        sys.exit(1)

    password = sys.argv[1]
    asyncio.run(test_steps(password))
