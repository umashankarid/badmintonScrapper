# Manual test plan — UI redesign (PR #5)

Everything on this branch was verified by machine. This is the pass that only a
person can do: does it look right, does it feel right, and does every flow still
work at both widths. Work through it top to bottom; the admin setup in
scenario 1 is a prerequisite for everything after it.

Estimated time: 60–90 minutes for the full pass.

## 0. Setup

1. In PowerShell, from the repo root: `.\run-local.ps1`
   Open **http://localhost:3002/** (or `http://oky-pc.taile089d6.ts.net:3002/` from
   the Mac or phone).
2. A bar at the top says **LIVE — real Badminton Sweden**. Click **Switch to DEV**.
   The bar turns orange: *DEV — fake data, nothing leaves this machine*.
   Dev mode is per process — every restart of `run-local.ps1` comes back LIVE.
3. Sign in through the bar's **Sign in as…** dropdown. It lists eight personas;
   the scenarios below say which to use. Signing in as another persona signs the
   first one out.
4. **Two widths for every scenario.** In Chrome: F12 → Ctrl+Shift+M for the
   device toolbar. Use **375 × 812** ("iPhone SE"-ish) and **Responsive at 1280
   wide**. Scenario 13 adds **exactly 768** and your full monitor width.
   From a real phone over Tailscale is better than the emulator for anything
   involving tapping.
5. **Below 768px the five admin tabs are behind a "Menu" button** under the
   topbar. Tap it for a vertical list, one row per section, current section
   tinted. Wherever a scenario says "go to X", that is how you get there on a
   phone.
6. **Reloading is enough for template and CSS changes** — they are read from
   disk per request. Only a change to `app.py` needs the server restarted. On
   a phone, Chrome's pull-to-refresh sometimes serves a cached page; use
   ⋮ → Reload or a new tab if something looks stale.
7. Registrations persist in `data-local\` between runs. Nothing below needs a
   clean slate. If you want one anyway: stop the app, delete
   `data-local\tournaments.db`, start it again — **that also deletes any real
   tournaments you set up locally.**

**How to report:** page, persona, width, what you did, what you saw, what you
expected, screenshot. Scenario 14 lists three bugs that predate this branch —
don't file those as regressions.

### Personas

| Sign in as | Who | Use for |
|---|---|---|
| `sbf04959` | Klubb Kontot — the club account, admin, no player profile | every admin page |
| `adam` | Adam Adult, 31, SENIOR, A-level points | ordinary registration, doubles, accommodation |
| `elin` | Elin Elit, 27, DS 8000 points | "points exceed maximum" refusal |
| `jonas` | Jonas Junior, 15, LEVEL 3-5 | "SJT category" refusal |
| `mini` | Mini Minior, 11 | under-13 dispens confirmation |
| `sara` | Sara Sexan, 16, LEVEL_6 | allowed in SJT (the positive control) |
| `pia`, `per` | another club | **cannot sign in** — used as doubles/mixed partners via search |

### Fixture tournaments (appear once scenario 1 makes them visible)

| Name | Classes | Registration closes |
|---|---|---|
| Dev Open (FAKE) | HS A, HS B, DS A, DS B, HD A, DD B, MD B | 2026-09-24 |
| Dev SJT Cup (FAKE) | HS U15, DS U15, MJT HS U13, MJT DS U13 | 2026-10-01 |
| Dev Away Weekend (FAKE) | HS B, DS B, HD B, DD B, MD B — accommodation & transport | 2026-10-08 |
| Dev Past Cup (FAKE) | (finished in August) — only on Previous Tournaments | — |

---

## 1. Admin: make the fixtures visible — `sbf04959`

**First, create the groups** — the Groups box on Add/Remove only offers groups
an admin has defined, and a fresh local DB has none:

- [ ] **Manage → Manage Komet Players → Add Groups** tab. Add three groups,
      spelled exactly like this, because the dev personas carry these names:
      `SENIOR`, `LEVEL 3-5`, `LEVEL_6`. Each appears in the list below the
      form as you add it.

Page: **Add/Remove** in the admin nav (`/add-remove-tournaments.html`).

- [ ] **On a wide screen (1280+):** each tournament is one row — checkbox,
      name and facts on the left; **Reg. deadline / Groups / Accommodation as
      one horizontal strip immediately beside them**, not pushed to the far
      edge. The row is about as tall as the facts, not twice that.
- [ ] **Narrow the window to ~900px** (a laptop, or half a screen): the strip
      no longer fits beside the facts and drops **underneath** them, still
      horizontal. Nothing else changes — no new breakpoint, the row decides.
- [ ] The checkbox lines up with the **first** line of its label (the
      tournament name), not the second.
- [ ] Under each name, three labelled facts — **PLAYS**, **REGISTRATION
      CLOSES**, **CLASSES** — not three grey lines. Classes are pills, one per
      class. The deadline reads *2026-09-24 · in N days*, and turns amber only
      when N is 7 or less. At 1280 the labels sit in a column to the left of
      their values; at 375 each label sits above its value.
- [ ] At 375 the same row stacks vertically and nothing scrolls sideways.
- [ ] **Dev Open**, **Dev SJT Cup** and **Dev Away Weekend** are listed. Tick
      all three. **Dev Past Cup** may or may not be here: the first load of the
      day fetches it, but the cache write drops it, so every later load that
      day shows three (pre-existing, see scenario 14, bug 4). Either is fine —
      if it is there, leave it unticked; it belongs to scenario 10.
- [ ] Groups: the box now offers the three groups you created. For Dev Open
      and Dev Away Weekend select **SENIOR**; for Dev SJT Cup select
      **LEVEL 3-5** and **LEVEL_6** (Ctrl-click for multiple; on a phone,
      tap each).
- [ ] For Dev Away Weekend tick **Accommodation & Transport**.
- [ ] Click **Save Selected Tournaments** → a native confirmation dialog, then
      the page reloads with the boxes still ticked.
- [ ] Open **How groups work**. **375:** three rules — *With groups / No
      groups / Admins* — as short sentences, no table. **1280:** a table
      instead, whose columns are *Who sees it* (green) and *Who does not*
      (red), so no cell just says "Hidden". Both widths: four examples with
      the groups as pills, and a one-line Ctrl/Cmd tip that reads as advice
      for a computer, not an instruction on a phone.

## 2. Player: tournament list — `adam`

Page: `/` (sign in via the bar; it lands here).

- [ ] Header: *Adam Adult (DEV-0001)* and a **Logout** button, no admin nav.
- [ ] Dev Open and Dev Away Weekend are listed. Dev SJT Cup is **not** (Adam is
      SENIOR; that one is juniors-only). Dev Past Cup is not.
- [ ] Each card shows name, place, dates, and a deadline line — *N days left*
      in amber when within a week, grey otherwise. No coloured stripe down the
      left edge, no shadow.
- [ ] **1280:** card is sideways — details left, deadline/badge/button right.
      The list is one column, not a grid.
- [ ] **375:** card is stacked, button full width.
- [ ] **Reminders on** → click → **Reminders off** and back. No page jump.
- [ ] `FAKE` badge on each card — expected in dev mode.
- [ ] **Logout** → the login card appears in the middle of the page, with real
      labels above the fields (not placeholder-only) and a *Skapa konto* panel
      below. No gradient bar across the top of the card.

## 3. Player: register for singles — `adam`, Dev Open

- [ ] Click **Dev Open** → registration page. *Back to tournaments* link top
      left, tournament name as the heading.
- [ ] **1280:** the form is one column on the left (never two columns of
      pickers); an identity panel — *REGISTERING / Adam Adult (DEV-0001) /
      BMK Komet / Registration closes …* — sits to its **right**.
- [ ] **375:** the identity panel sits **above** the form.
- [ ] Three pickers: Singles, Doubles, Mixed — each with an uppercase label
      above, each full width at 375.
- [ ] Singles → **HS A**. Leave the others. Click **Register**.
- [ ] Button text becomes **Update**; a green *Du är redan anmäld…* panel
      appears above the form; **My Registration** below lists one row: Adam,
      DEV-0001, BMK Komet, Male, email, phone, HS A.
- [ ] **1280 table:** DEV-0001 stays on one line; **Edit** and **Withdraw** sit
      side by side on one line; row is single-height.
- [ ] **375 table:** stacks as `NAME Adam Adult / LICENSE ID DEV-0001 / …`.
      There is **no** `DOUBLES` or `MIXED` label with nothing after it.
- [ ] **Withdraw** → native confirmation → the row disappears and the button
      reads **Register** again.

## 4. Player: doubles with a partner — `adam`, Dev Open

- [ ] Doubles → **HD A**. A partner search box appears below it.
- [ ] Type `Per`. A dropdown lists **Per Partner (DEV-0007)**. At 375 the
      dropdown is not clipped by the screen edge.
- [ ] Click it → the field fills with the name. Empty the field → the dropdown
      disappears (no empty bordered box left behind).
- [ ] Register → the row shows *HD A (Per Partner)* under Doubles.
- [ ] Withdraw.

## 5. Player: the refusals — one persona each, Dev Open

The point of this scenario: a refusal is now a **panel above the button** that
says what blocked you and why, not a browser popup. Each one should scroll into
view at 375 and disappear the next time you press the button.

**`jonas`** (15, LEVEL 3-5)
- [ ] Singles → **HS B** → Register.
- [ ] A red panel appears above the button: title **Cannot register**, detail
      mentioning *är en SJT-kategori (Nivå 6)*. No popup.
- [ ] My Registration stays empty — the refusal refused.
- [ ] Change Singles to something else and press again → the old panel is gone
      before the new result shows.

**`elin`** (DS 8000 points)
- [ ] Singles → **DS A** → Register.
- [ ] Red panel: **Cannot register**, detail with *exceed maximum*. No row.

**`sara`** (16, LEVEL_6) — positive control
- [ ] Singles → **DS B** → Register → **succeeds**, row appears. Withdraw.

**`mini`** (11)
- [ ] Singles → **DS B** → Register.
- [ ] This one is a **native confirm** dialog asking about *tillstånd
      (dispens)* — it is a question, not a refusal, so it stays a dialog.
      Cancel → no row. OK → row appears. Withdraw.

**`pia`** (other club)
- [ ] Sign in as Pia from the bar → a native dialog says she is not a Komet
      member. She is not signed in.

**Nothing selected** — `adam`
- [ ] Leave all three pickers empty → Register → panel **Pick a category
      first**.

**Also check on the refusal panel:**
- [ ] It reads correctly with colour taken away — the title says the outcome.
- [ ] At 375, after pressing the button the page scrolls so the panel is
      visible above the button.
- [ ] The detail text keeps its line breaks (Swedish line, then English line).

## 6. Player: accommodation & transport — `adam`, Dev Away Weekend

- [ ] Open Dev Away Weekend. Below the pickers an inset panel has three
      checkbox rows: **Need accommodation**, **Need transport**, **Can offer
      rides**. Each row is comfortably tall to tap and there is clear space
      between them (they do not touch).
- [ ] Tick **Need accommodation** → a count field and an ages field appear.
      Count = 2, ages **empty**. Singles → HS B → Register.
- [ ] Red panel **Ages missing** (Swedish and English). No row.
- [ ] Fill ages `31, 8` → Register → row appears. **Leave it in place** — the
      *Accommodation 2* badge only shows on the admin view, and scenario 8
      checks it there.

## 7. Player: the warnings panel on load

- [ ] `elin` → open Dev Open. Under the heading **Registration problems** a red
      panel reads **Not allowed** / *Points too high for …*. No orange stripe
      down its left edge, no emoji.
- [ ] `mini` → open Dev Open → an amber panel *Must be at least 13 to play …*.
- [ ] `adam` → open Dev Open → **no** warnings panel at all.

## 8. Admin: registrations on a tournament — `sbf04959`

Before this, register a couple of players so there is data: `adam` HS A and
`sara` DS B in Dev Open (scenarios 3 and 5).

- [ ] Open `/` → the admin sees the nav tabs and a *N registered* badge on each
      card instead of a Register button. Click **Dev Open**.
- [ ] The page is the **admin view**: no player form; instead an **Add / Edit
      Player (Admin)** card with a player search, and below it a per-class
      list of players. Each class table has **Edit** and **Delete** on one
      line per row.
- [ ] **Admin refusal.** In the search box type `Jonas` → pick **Jonas Junior**
      → Singles **HS B** → **Add Player**. A red panel **Registration failed**
      with *är en SJT-kategori (Nivå 6)* appears **directly above the Add
      Player button** — not a popup, and not invisible. No row is added.
- [ ] **Edit** on Adam → the card's title becomes *Edit Player (Admin)* and the
      button **Update**. Singles → **HS B** → Update → Adam's row moves to the
      HS B table.
- [ ] **Delete** on Sara → native confirm → row gone.
- [ ] Open **Dev Away Weekend** as admin → Adam's row (left in place in
      scenario 6) shows an **Accommodation 2** badge after his name.
- [ ] 375: every class table stacks; Edit/Delete still side by side.

## 9. Admin: Manage Tournaments — `sbf04959`

Page: **Tournaments for Registration** tab.

- [ ] Two tabs — **View Registrations** / **Add/Remove Tournaments** — and the
      active one is visibly different (blue text, blue underline). **Manage DB →**
      sits at the right as a link, not a third tab.
- [ ] Click the second tab → active state moves; the first panel hides.
- [ ] Dev Open card: **View / Edit / Download CSV / Delete** on one line with
      gaps. Download CSV → a file downloads. **Edit** → see scenario 14 (known
      broken before this branch). Do **not** press Delete.
- [ ] **Show Point Rules** → a wide table. 1280: real table. **375: it stacks
      and does not scroll sideways** — this table was the worst offender.
      **Edit** → cells become inputs → **Cancel**.
- [ ] **Show Email Settings** → SMTP form, each input with a label. Don't save.

## 10. Admin: Manage hub and the pages under it — `sbf04959`

**Manage** tab.
- [ ] Four tiles. Hover one at 1280 → border turns blue and **nothing
      underlines** (not the heading, not the description). No coloured stripe.

**Manage Admins**
- [ ] Topbar with the admin name and Logout is present (it was missing here
      before). Add an admin by license ID `DEV-0001` → green *added* banner
      with no check-mark emoji. **Remove it straight away** — otherwise Adam
      is an admin for the rest of the pass and scenarios 2–7 stop making
      sense. Error case: an unknown id → red *Error:* banner.

**Manage Komet Players**
- [ ] Tabs with an active state. Search box and group filter each work (they
      have labels for screen readers; you won't see them).
- [ ] **1280:** each row is a person — name in bold with the licence in grey
      beneath it, then Email, then Groups as pills. Anything missing shows a
      faint **—**, never a blank cell; a player with no licence says *no
      licence*. Edit/Delete hug the right edge of the row.
- [ ] **375:** each player is a card — name as the title, licence beneath,
      pills if any, Edit/Delete under that. **No** `NAME` or `ACTIONS`
      labels; a row with no email simply has no email line.
- [ ] Below the list: *N players*. Paging (← Prev / Next →, "Page 1 of 2")
      only appears when there is a second page; with a handful of players
      there is nothing there at all.

**Manage Database**
- [ ] Statistics as four boxes with big blue numbers; the small captions under
      them are readable (dark enough) on the tinted background.
- [ ] **Create Backup** → appears in the list → **Delete** it (confirm).
- [ ] **Clean Orphaned Registrations** → native confirm → **Cancel** (it deletes
      across every tournament).
- [ ] Click a database → its tables → click a table → data modal. **1280:** a
      long cell clips with an ellipsis instead of widening the page (hover it
      for the full value). **375:** the same cell **wraps** instead — stacked
      rows own the full width, so clipping would only hide text.

**Email Settings**
- [ ] Section sub-headings are bold body size, consistently. The events/bounce
      table: any long Reason cell is clipped with an ellipsis at 1280 and does
      **not** push the page into horizontal scroll. Don't press Send/Test.

**Send Email**
- [ ] The message body has a **rich-text toolbar** — Bold, Italic, Underline,
      size, colour, lists. Type a line, select it, press **B** → it goes bold.
      Colour dropdown offers five club colours; Purple is gone on purpose.
      Do **not** send.
- [ ] The editable area looks like the other fields (same border, radius).

**Previous Tournaments**
- [ ] Dev Past Cup is listed as a card; the whole card is a link. Click → the
      detail page: *Back to tournaments* link, medal badges say the word
      (**Gold/Silver/Bronze**) not just a colour, match cards show **Won/Lost**
      as a badge. Click a club → its table → Back. 375: everything stacks.

## 11. Login page

- [ ] `/login.html` signed out: one card, labels above both fields, blue
      full-width button. Wrong password → red panel under the button.

## 12. Every page, both widths — the sweep

Sign in as `sbf04959` and open each in turn at 375 **and** 1280. At each:
- [ ] Nothing scrolls sideways.
- [ ] **1280:** the admin nav is one row of tabs and the current section is
      blue with a blue underline (the four Manage sub-pages highlight nothing —
      expected).
- [ ] **375:** the tabs are behind a **Menu** button. The button is the same
      compact size on every page — it should never stretch the full width. Open
      it: a vertical list, one 44px row per section, current section tinted.
- [ ] Buttons in a row have visible space between them.
- [ ] No emoji anywhere, no coloured left borders, no drop shadows.
- [ ] Content fills the width with even margins; on a short page the footer
      sits at the bottom of the screen, on a long one it follows the content.
- [ ] Footer *Behöver du hjälp?* with the support link.

Pages: `/`, `/tournament.html?url=https://dev.local/tournament/DEV-T1`,
`/manage-tournaments.html`, `/add-remove-tournaments.html`, `/manage.html`,
`/manage-admins.html`, `/manage-komet-players.html`, `/manage-db.html`,
`/email-settings.html`, `/send-email.html`, `/results.html`,
`/tournament-detail.html?id=DEV-T3`, `/login.html` (signed out).

## 13. Things no machine has checked

- [ ] **Exactly 768 wide** (iPad portrait): the tournament list card goes
      sideways **and** the admin tables are still real tables — not one
      desktop and the other phone. The Menu button is gone and the tabs are
      back in a row.
- [ ] **767 wide**, one pixel narrower: tables stack and the Menu button
      appears. Nothing should be in both states at either width.
- [ ] **Your full monitor width** (wider than 1440): content centres at 1440
      with the page background filling the rest evenly — not stretched edge to
      edge, not stranded in a narrow column. The footer still spans the full
      width.
- [ ] **Keyboard only** on the registration page at 1280: Tab from the top —
      the order goes *Back link → pickers → Register* and never jumps into the
      identity panel on the right (it holds nothing focusable). Every focused
      element shows a **blue outline**, including inside the tinted panel.
- [ ] **Hover** every button style once: primary blue, secondary white,
      danger red — each changes on hover, none underlines.
- [ ] **Zoom to 200%** on the registration page: still one column, still
      usable, no overlap.
- [ ] **Real data:** if you have a real local tournament, open it as admin —
      the class tables with real names and long emails; does the ten-column
      table hold up.
- [ ] **Another browser:** Safari on the Mac or iPhone, and Firefox if
      installed. The sticky identity panel, the partner dropdown, and the
      stacked table labels are the three things most likely to differ.
- [ ] **Read the Swedish.** The refusal and warning texts are bilingual; a
      speaker should check they read naturally and the Swedish line comes first.

## 14. Known before this branch — not regressions

1. **Changing a level picker never validates client-side.** The handler that
   should warn you as you pick has a bug (`e` is undefined) and has silently
   never run. The rules are still enforced when you press Register — you just
   get no early warning.
2. **Manage Tournaments → Edit throws.** `editTournament()` reads a `levels`
   field the API doesn't return. The Edit button has been broken for every
   tournament.
3. **The admin search box on a tournament page filters nothing** — it targets
   a table the admin view never fills.
4. **Add/Remove shows a different list on the first load of the day than on
   later loads.** The fresh fetch returns every tournament the feed has
   (four in dev mode, including the finished Dev Past Cup); but the
   per-tournament detail fetch fails for a finished tournament, failed
   fetches are never written to the cache, so every later load that day
   shows three. Neither is wrong, but they disagree, and Hard Refresh brings
   the fourth back until the next load.

File anything else you find.
