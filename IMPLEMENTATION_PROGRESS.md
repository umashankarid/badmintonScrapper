# Players.db Refactor - Implementation Progress

**Status**: ✅ **PHASE 2 COMPLETE** - Scraper module created  
**Date**: 2026-08-13  
**Progress**: 2 of 4 phases done (50%)

---

## ✅ COMPLETED

### Phase 1: Database Migration ✅
- ✅ Backed up original players.db
- ✅ Migrated 824 players to new schema
- ✅ Changed primary key from `id` → `license_id`
- ✅ Added 6 new columns:
  - `email`, `phone`, `dob`, `age`, `ranking`, `last_updated`, `last_scraped`
- ✅ Verified: All 12 unit tests still passing
- ✅ Updated `init_players_db()` function in app.py

**Files**:
- `migrate_players_db.py` - Migration script (one-time use)
- `app.py` - Updated init function
- Backup: `players.db.backup.20260813_104226`

### Phase 2: Scraper Module ✅
- ✅ Created `players_scraper.py` module with functions:
  - `scrape_all_players()` - Bulk scrape on startup
  - `scrape_player_by_license_id()` - Individual scrape on login
  - `scrape_ranking_from_page()` - Extract ranking JSON
  - `update_player_in_db()` - Insert/update players.db
  - `get_player_by_license_id()` - Query from players.db

**Files**:
- `players_scraper.py` - 298 lines, complete scraper module

---

## ⏳ IN PROGRESS

### Phase 3: Integration with App (NEXT)
**Tasks**:
- [ ] Import `players_scraper` into `app.py`
- [ ] Call `scrape_all_players()` on startup (in run_startup_tests)
- [ ] Call `scrape_player_by_license_id()` on user login
- [ ] Update player lookup functions to use `license_id`
- [ ] Update registration flow

**Estimated effort**: 2-3 hours

### Phase 4: Tournament Registration Tables (AFTER Phase 3)
**Tasks**:
- [ ] Create dynamic table creation for `tournament_<id>_registrations`
- [ ] Update registration endpoints
- [ ] Reference players.db instead of duplicating data
- [ ] Test end-to-end registration flow

**Estimated effort**: 2-3 hours

---

## 📊 Current Database State

### players.db (140 KB, 824 rows)
```
NEW SCHEMA (active):
✅ license_id (TEXT PRIMARY KEY)
✅ name (TEXT NOT NULL)
✅ profile_url (TEXT)
✅ club (TEXT)
✅ gender (TEXT)
✅ email (TEXT)
✅ phone (TEXT)
✅ dob (TEXT)
✅ age (TEXT)
✅ ranking (TEXT) - JSON format
✅ last_updated (TIMESTAMP)
✅ last_scraped (TIMESTAMP)

MIGRATION NOTES:
- license_id values: temp_1, temp_3, temp_5... (will be updated from Badminton Sweden)
- All 824 players successfully migrated
```

### admin.db (40 KB) ✅
```
CLEAN STRUCTURE:
✅ admin_users (2 rows)
✅ smtp_settings (0 rows - ready for future)
✅ reminders_sent (0 rows - ready for future)

REMOVED:
❌ bwf_tournament_visibility
❌ tournament_visibility (legacy)
```

### point_rules.db (12 KB) ✅
```
UNCHANGED:
✅ point_rules (5 rows)
```

### tournaments.db ❌
```
NOT YET CREATED:
- Should be created in Phase 3/4
- Will contain:
  • tournaments table (metadata)
  • tournament_<id>_registrations tables (per-tournament registrations)
```

---

## 🔄 Data Flow (Planned)

### On Application Startup
```
1. app.py starts
2. run_startup_tests() runs ✅
3. download_all() from Dropbox ✅
4. init_players_db() - create table if needed ✅
5. [PHASE 3] scrape_all_players() from Badminton Sweden
   ├─ Searches for all players
   ├─ Updates license_ids (replace temp_X with real ones)
   ├─ Populates rankings
   └─ All 824+ players current
```

### On User Login
```
1. User logs in with email/username
2. [PHASE 3] Look up license_id from players.db
3. [PHASE 3] Call scrape_player_by_license_id(license_id)
4. Fetch fresh data from Badminton Sweden
5. Compare with players.db
6. Update if changed (ranking, club, age, etc.)
7. Set last_updated = NOW()
8. Result: User's data is current
```

### On Player Registration for Tournament
```
1. User registers for tournament
2. Get license_id from user/session
3. Query players.db (read-only, reference only)
4. [PHASE 4] Insert into tournament_<id>_registrations
5. Store: license_id, levels, partners, date
6. Result: Registration stored, no data duplication
```

---

## 🎯 Next Actions

### Before Phase 3 Integration:
1. ✅ Verify players_scraper.py is working
2. ✅ Test scraping individual players
3. Test bulk scraping (optional - time-consuming)

### Phase 3 Tasks (When Ready):
1. Import players_scraper in app.py
2. Add scrape_all_players() to startup
3. Add scrape_player_by_license_id() to login flow
4. Update player lookup functions
5. Test all flows

---

## ✅ Quality Assurance

- ✅ All code has proper error handling
- ✅ All functions have docstrings
- ✅ Logging added for debugging
- ✅ Syntax verified (python3 -m py_compile)
- ✅ Unit tests still passing (12/12)
- ✅ No breaking changes to existing code

---

## 📝 Files Created/Modified This Session

**Created**:
- `migrate_players_db.py` - Migration script
- `PLAYERS_DB_REFACTOR_PLAN.md` - Design document
- `PLAYER_DATA_ANALYSIS.md` - Data discovery
- `players_scraper.py` - Scraper module
- `ACTUAL_DB_STRUCTURE.md` - Current state documentation

**Modified**:
- `app.py` - Updated init_players_db()
- `admin.db` - Cleaned up tables
- `players.db` - Schema migrated

**Backups**:
- `players.db.backup.20260813_104226` - Keep until verified
- `admin.db.backup.20260813_103231` - Keep until verified

---

## 🚀 Ready for Next Phase?

Once Phase 3 integration starts, we'll:
1. Connect players_scraper to app startup
2. Test bulk player scraping (first time, updates license_ids)
3. Test individual player scraping on login
4. Verify rankings are current
5. Move to tournament registration integration

**Estimated total time**: ~4-5 hours from here

---

## 📞 Questions/Notes

- Bulk scraping on startup will take time (depends on Badminton Sweden server)
- Consider rate limiting to avoid overwhelming server
- Could cache player data locally to speed up lookups
- Ranking JSON format is flexible for future categories

**Status**: Ready to proceed to Phase 3 when you give the go-ahead! ✅
