"""
test_bwf_doubles.py — Explore the doubles popup structure without saving.
Navigates to composition page, clicks "Lägg till dubbel" and captures the popup.
Clicks Avbryt at the end (no save).
"""

import asyncio
import sys

BASE_URL = "https://badmintonsweden.tournamentsoftware.com"
TOURNAMENT_ID = "A2AB5259-7C92-4A4D-88C1-CC7A0C6DCD4F"
CLUB_LOGIN = "sbf04959"


async def test_doubles(password: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)

        try:
            # ===== Login =====
            print("Logging in...")
            print("  goto /user...")
            await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            print(f"  URL: {page.url}")

            cookie_btn = await page.query_selector('a:has-text("JAG GODKÄNNER")')
            if not cookie_btn:
                cookie_btn = await page.query_selector('button:has-text("JAG GODKÄNNER")')
            if not cookie_btn:
                cookie_btn = await page.query_selector('a:has-text("Jag godkänner")')
            if not cookie_btn:
                # Try finding by evaluating JS
                found = await page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('a, button, input');
                        for (const el of els) {
                            if (el.textContent.trim().toUpperCase() === 'JAG GODKÄNNER') {
                                el.click(); return true;
                            }
                        }
                        return false;
                    }
                """)
                if found:
                    print("  Clicked cookie via JS")
                    await page.wait_for_timeout(5000)
                else:
                    print("  No cookie button found at all")
            if cookie_btn:
                print("  Clicking cookie button...")
                await cookie_btn.click()
                await page.wait_for_timeout(5000)
            else:
                print("  No cookie wall")

            print(f"  URL after cookie: {page.url}")
            if "cookiewall" in page.url:
                print("  Still on cookiewall, navigating...")
                await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

            # Wait for login form
            print(f"  URL before login: {page.url}")
            login_input = await page.query_selector('input[name="Login"]')
            if not login_input:
                print("  No login input found, trying goto...")
                await page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                login_input = await page.query_selector('input[name="Login"]')
                if not login_input:
                    print("  ❌ Still no login input!")
                    body = await page.inner_text("body")
                    print(f"  Page: {body[:300]}")
                    await browser.close()
                    return

            print("  Filling login...")
            await page.fill('input[name="Login"]', CLUB_LOGIN)
            await page.fill('input[name="Password"]', password)
            submit_btn = await page.query_selector('button[type="submit"]') or await page.query_selector('input[type="submit"]')
            if submit_btn:
                print("  Clicking submit...")
                await submit_btn.click()
            await page.wait_for_timeout(5000)
            print("✅ Logged in")

            # ===== Navigate to entry =====
            entry_url = f"{BASE_URL}/onlineentry/onlineentry.aspx?id={TOURNAMENT_ID}"
            await page.goto(entry_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # Click group entry
            group_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnGroupEntry')
            await group_btn.click()
            await page.wait_for_timeout(5000)

            # Accept terms
            agree_cb = await page.query_selector('#cphPage_cphPage_cphPage_VF1_fs0_agree')
            if agree_cb and not await agree_cb.is_checked():
                await agree_cb.check()
            next_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_0')
            await next_btn.click()
            await page.wait_for_timeout(5000)

            # Fill team manager
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerfirstname', 'Andi')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerlastname', 'Tandaputra')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanageremail', 'Tavlingar@bmkkomet.se')
            await page.fill('#cphPage_cphPage_cphPage_VF2_fs0_teammanagerphone', '0732103066')
            next_btn2 = await page.query_selector('#cphPage_cphPage_cphPage_btnNext_1')
            await next_btn2.click()
            await page.wait_for_timeout(5000)
            print("✅ On composition page")

            # ===== Click first "Lägg till dubbel" =====
            print("\nClicking first 'Lägg till dubbel'...")
            doubles_links = await page.query_selector_all('a:has-text("Lägg till dubbel")')
            print(f"Found {len(doubles_links)} 'Lägg till dubbel' links")

            if not doubles_links:
                print("❌ No doubles links found")
                await browser.close()
                return

            await doubles_links[0].click()
            await page.wait_for_timeout(3000)

            # ===== Capture popup structure =====
            print("\n" + "=" * 60)
            print("DOUBLES POPUP CONTENT:")
            print("=" * 60)

            await page.screenshot(path="bwf_doubles_popup.png", full_page=True)
            print("📸 Screenshot: bwf_doubles_popup.png")

            # Get the dialog content
            body_text = await page.inner_text("body")
            # Find dialog section
            if "Välj" in body_text:
                idx = body_text.index("Välj")
                print(f"\nDialog text:\n{body_text[idx:idx+1000]}")

            # Look for all UL elements (player lists)
            ul_info = await page.evaluate("""
                () => {
                    const uls = document.querySelectorAll('ul');
                    return Array.from(uls).filter(ul => ul.id || ul.children.length > 0).map(ul => ({
                        id: ul.id,
                        classes: ul.className,
                        childCount: ul.children.length,
                        visible: ul.offsetParent !== null,
                        firstChildren: Array.from(ul.children).slice(0, 3).map(li => li.textContent.trim().substring(0, 80)),
                        parentId: ul.parentElement ? ul.parentElement.id : '',
                        parentClass: ul.parentElement ? ul.parentElement.className.substring(0, 50) : ''
                    }));
                }
            """)
            print("\nAll UL elements with content:")
            for ul in ul_info:
                if ul['childCount'] > 0 and ul['visible']:
                    print(f"  <ul id='{ul['id']}' class='{ul['classes'][:40]}' children={ul['childCount']} parent='{ul['parentClass']}'")
                    for child in ul['firstChildren']:
                        print(f"    - {child}")

            # Look for select elements
            select_info = await page.evaluate("""
                () => {
                    const selects = document.querySelectorAll('select');
                    return Array.from(selects).filter(s => s.offsetParent !== null || s.options.length > 1).map(s => ({
                        id: s.id,
                        name: s.name,
                        size: s.size,
                        visible: s.offsetParent !== null,
                        optionCount: s.options.length,
                        firstOptions: Array.from(s.options).slice(0, 5).map(o => o.text.trim().substring(0, 60))
                    }));
                }
            """)
            print("\nSelect elements:")
            for s in select_info:
                if s['optionCount'] > 0:
                    print(f"  <select id='{s['id']}' visible={s['visible']} size={s['size']} opts={s['optionCount']}: {s['firstOptions']}")

            # Look for input fields in the dialog
            input_info = await page.evaluate("""
                () => {
                    const dialog = document.querySelector('.ui-dialog-content') || document.querySelector('.ui-dialog');
                    if (!dialog) return [];
                    const inputs = dialog.querySelectorAll('input, select, button, a');
                    return Array.from(inputs).map(el => ({
                        tag: el.tagName,
                        type: el.type || '',
                        id: el.id,
                        name: el.name || '',
                        value: (el.value || '').substring(0, 50),
                        text: (el.textContent || '').trim().substring(0, 50),
                        visible: el.offsetParent !== null,
                        placeholder: el.placeholder || ''
                    }));
                }
            """)
            print("\nElements inside dialog:")
            for inp in input_info:
                if inp['visible'] or inp['id']:
                    print(f"  <{inp['tag']}> type='{inp['type']}' id='{inp['id']}' value='{inp['value']}' text='{inp['text']}'")

            # Check the full dialog HTML structure
            dialog_html = await page.evaluate("""
                () => {
                    const dialog = document.querySelector('#cphPage_cphPage_cphPage_dlgDouble') || 
                                   document.querySelector('.ui-dialog-content[id*="Double"]') ||
                                   document.querySelector('.ui-dialog-content');
                    if (!dialog) return 'No dialog found';
                    return dialog.innerHTML.substring(0, 3000);
                }
            """)
            print(f"\nDialog HTML (first 3000 chars):\n{dialog_html}")

            # ===== Click Avbryt to cancel =====
            print("\n\nClicking 'Avbryt' to cancel...")
            cancelled = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        if (a.textContent.trim() === 'Avbryt' && a.offsetParent !== null) {
                            a.click(); return true;
                        }
                    }
                    return false;
                }
            """)
            if cancelled:
                print("✅ Cancelled (no save)")
            else:
                print("⚠️ Could not find Avbryt, clicking Cancel button...")
                cancel_btn = await page.query_selector('#cphPage_cphPage_cphPage_btnCancel_2')
                if cancel_btn:
                    await cancel_btn.click()
                    print("✅ Clicked Cancel")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            await page.screenshot(path="bwf_doubles_error.png", full_page=True)
        finally:
            await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_bwf_doubles.py <password>")
        sys.exit(1)
    asyncio.run(test_doubles(sys.argv[1]))
