# BWF Submission Flow — Final Confirmed Steps

**Status: TESTED AND WORKING** ✅  
**Test date:** 2026-08-15  
**Test result:** Successfully registered Kavin Ananda Sentraya Perumal for HS U11 in Komet Hösttävling 2026

---

## Complete Flow

### Step 1: Accept Cookie Wall
- Navigate to `https://badmintonsweden.tournamentsoftware.com/user`
- Click `a:has-text("JAG GODKÄNNER")` if cookie wall is shown

### Step 2: Login
- Fill `input[name="Login"]` with club login (sbf04959)
- Fill `input[name="Password"]` with password
- Click submit
- Verify: no `input[name="Login"]` on page = success

### Step 3: Navigate to Online Entry
- URL: `https://badmintonsweden.tournamentsoftware.com/onlineentry/onlineentry.aspx?id={tournament_id}`
- Tournament ID extracted from stored `tournament_url`

### Step 4: Click Group Entry
- Click `#cphPage_cphPage_cphPage_btnGroupEntry` ("Online-anmälan som grupp")

### Step 5: Accept Terms + Next
- Check `#cphPage_cphPage_cphPage_VF1_fs0_agree` ("Jag godkänner")
- Click `#cphPage_cphPage_cphPage_btnNext_0` ("Nästa")

### Step 6: Fill Team Manager + Next
- `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerfirstname` → "Andi"
- `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerlastname` → "Tandaputra"
- `#cphPage_cphPage_cphPage_VF2_fs0_teammanageremail` → "Tavlingar@bmkkomet.se"
- `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerphone` → "0732103066"
- Click `#cphPage_cphPage_cphPage_btnNext_1` ("Nästa")

### Step 7: Player Composition Page — Add Singles Players
For each event + player:
1. Click the correct "Lägg till spelare" link (mapped by index to event name)
2. **Popup opens:** jQuery UI dialog with title "Välj spelare för {EVENT}"
3. Player list is in `<ul id="ULAvailablePersons">` with `<li>` items
4. Click `#ULAvailablePersons li:has-text("{player_first_name}")` to select
5. Click `#cphPage_cphPage_cphPage_btnAddPersonToSelection` ("Lägg till>>") via JS
6. Click "Ok" button in dialog (via JS: find `a` with text "Ok")

### Step 8: Player Composition Page — Add Doubles Pairs
For each doubles/mixed event + pair:
1. Click the correct "Lägg till dubbel" link
2. **Popup opens:** jQuery UI dialog "Välj spelare för {EVENT}"
3. Two player lists:
   - `<ul id="ULPair1">` — **Player 1** (club members only, e.g. 8 players)
   - `<ul id="ULPair2">` — **Player 2** (ALL players from all clubs, 127+, includes `<Partner önskas>`)
4. Click player 1 `<li>` in `#ULPair1`
5. Click player 2 `<li>` in `#ULPair2`
6. Click `#cphPage_cphPage_cphPage_btnAddPairToSelection` ("Lägg till>>") via JS
7. Click "Ok" button in dialog

### Step 9: Save
- Click `#cphPage_cphPage_cphPage_btnSubmit_2` ("Spara")
- Verify: page contains "Tack" or "slutfört" = success

---

## Key Selectors

| Element | Selector |
|---------|----------|
| Cookie accept | `a:has-text("JAG GODKÄNNER")` |
| Login field | `input[name="Login"]` |
| Password field | `input[name="Password"]` |
| Group entry button | `#cphPage_cphPage_cphPage_btnGroupEntry` |
| Terms checkbox | `#cphPage_cphPage_cphPage_VF1_fs0_agree` |
| Next (step 5) | `#cphPage_cphPage_cphPage_btnNext_0` |
| Team Manager first name | `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerfirstname` |
| Team Manager last name | `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerlastname` |
| Team Manager email | `#cphPage_cphPage_cphPage_VF2_fs0_teammanageremail` |
| Team Manager phone | `#cphPage_cphPage_cphPage_VF2_fs0_teammanagerphone` |
| Next (step 6) | `#cphPage_cphPage_cphPage_btnNext_1` |
| Add singles links | `a:has-text("Lägg till spelare")` |
| Add doubles links | `a:has-text("Lägg till dubbel")` |
| Available players list | `#ULAvailablePersons` |
| Add person button | `#cphPage_cphPage_cphPage_btnAddPersonToSelection` |
| Add pair button | `#cphPage_cphPage_cphPage_btnAddPairToSelection` |
| Save button | `#cphPage_cphPage_cphPage_btnSubmit_2` |

---

## Data Flow

```
tournaments.db                    BWF Site
─────────────                    ────────
tournament_url → tournament_id → /onlineentry/onlineentry.aspx?id={id}

tournament_registrations:
  singles_levels: "HS U11"      → Click "Lägg till spelare" for HS U11
  player_name: "Kavin..."       → Select from ULAvailablePersons popup
  
  doubles_levels: "DD U13"      → Click "Lägg till dubbel" for DD U13
  player + doubles_partner      → Select both from popup
```

---

## Implementation Files

- `bwf_submit.py` — Main Playwright automation module
- `app.py` — `/admin/submit-tournament` route (calls `submit_tournament_sync`)
- `templates/manage-tournaments.html` — "Submit to BWF" button UI
- `test_bwf_steps.py` — Step-by-step test script (for debugging)
