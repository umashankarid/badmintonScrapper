# Code Cleanup Analysis - Remove Per-Tournament DB References

## Current State

### ❌ What Still Exists in Code

**References to per-tournament DBs** (~47 matches in app.py):

1. **TOURNAMENTS_DIR constant and setup** (line 23-24)
   ```python
   TOURNAMENTS_DIR = os.path.join(os.path.dirname(__file__), "tournaments")
   os.makedirs(TOURNAMENTS_DIR, exist_ok=True)
   ```
   **Status**: Should be REMOVED (directory not used)

2. **get_tournament_db() function** (line 327)
   - Opens per-tournament DB files from tournaments/ directory
   - Used by legacy endpoints
   - **Status**: Should be REMOVED

3. **Functions still using db_file parameter**:
   - `/tournament-visibility/toggle` (line 1340s)
   - `/tournament-events` (line 1772)
   - `/register` (line 1840s)
   - Many others
   - **Status**: Need refactoring to use tournament_id instead

4. **get_tournament_events()** (line 1772+)
   - Expects `dbFile` query parameter
   - **Status**: Should use tournament_id from tournaments.db

5. **register_player() endpoint** (line ~1980)
   - Takes `dbFile` parameter
   - Saves to per-tournament DB
   - **Status**: Should save to tournaments.db → tournament_registrations table

---

## ✅ What's Already Good

1. ✅ tournaments/ directory is EMPTY (no legacy DB files)
2. ✅ tournaments.db doesn't exist yet (we'll create it properly)
3. ✅ drive_sync.py was updated to sync per-tournament DBs as interim fix
4. ✅ Unit tests don't reference tournament DB structure

---

## 📋 Cleanup Tasks Required

### Task 1: Remove TOURNAMENTS_DIR
- [ ] Remove lines 23-24 from app.py
- [ ] Remove all `TOURNAMENTS_DIR` references
- [ ] Remove all `db_file` path operations

### Task 2: Remove get_tournament_db() function
- [ ] Delete the function (line 327+)
- [ ] Update all 20+ callers

### Task 3: Refactor Legacy Endpoints

**Endpoints to update**:
1. `/api/tournament-visibility/toggle` (line 1340)
   - OLD: Uses `db_file` parameter
   - NEW: Use `tournament_id` parameter

2. `/api/tournament-events` (line 1772)
   - OLD: Expects `dbFile` query param
   - NEW: Use `tournament_id`, query tournaments.db

3. `/register` (player registration) (line 1840+)
   - OLD: Saves to tournaments/<tournament>.db
   - NEW: Save to tournaments.db → tournament_<id>_registrations

4. `/api/add-player` (line 1850+)
   - OLD: Uses `dbFile` parameter
   - NEW: Use `tournament_id`

5. `/api/delete-player` (line 1995+)
   - OLD: Uses `dbFile` parameter
   - NEW: Use `tournament_id`

6. `/api/get-players/<tournament>` (line 1610+)
   - OLD: Reads from tournaments/<tournament>.db
   - NEW: Query tournaments.db

7. Plus 10+ more endpoints

### Task 4: Create Proper tournaments.db Schema

```sql
CREATE TABLE tournaments (
    id INTEGER PRIMARY KEY,
    tournament_url TEXT UNIQUE NOT NULL,
    tournament_name TEXT NOT NULL,
    location TEXT,
    date_start TEXT,
    date_end TEXT,
    selected_for_view INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    last_updated TIMESTAMP
)

CREATE TABLE tournament_<id>_registrations (
    id INTEGER PRIMARY KEY,
    license_id TEXT NOT NULL,
    singles_level TEXT,
    doubles_level TEXT,
    mixed_level TEXT,
    doubles_partner TEXT,
    mixed_partner TEXT,
    registration_date TIMESTAMP,
    FOREIGN KEY (license_id) REFERENCES players(license_id)
)
```

### Task 5: Update drive_sync.py

Currently syncs:
- ❌ Root DBs
- ⚠️ tournaments/ directory (interim fix)

Should sync:
- ✅ Root DBs (players, admin, point_rules)
- ✅ tournaments.db (NEW - unified DB)
- ❌ tournaments/ directory (DELETE)

---

## 🔍 Code Complexity

### Current Situation
- **Per-tournament DB code**: ~500+ lines
- **Still in use**: YES (but shouldn't be)
- **Actually being used**: NO (tournaments/ is empty)
- **Testing coverage**: NO (unit tests don't cover this)

### After Cleanup
- **Unified tournament code**: ~200 lines
- **Simpler**: YES
- **Maintainable**: YES
- **Testable**: YES

---

## 📊 Endpoint Summary

| Endpoint | Current | Issue | Fix |
|----------|---------|-------|-----|
| `/api/tournament-visibility/toggle` | Uses db_file | Legacy | Use tournament_id |
| `/api/tournament-events` | Uses dbFile param | Legacy | Use tournament_id |
| `/register` | Saves to per-tournament DB | Legacy | Save to tournaments.db |
| `/api/add-player` | Uses dbFile | Legacy | Use tournament_id |
| `/api/delete-player` | Uses dbFile | Legacy | Use tournament_id |
| `/api/get-players/<tournament>` | Reads per-tournament DB | Legacy | Query tournaments.db |
| GET `/api/open-tournaments` | Works with admin.db | Modern | Keep as-is |
| POST `/api/bwf-tournament-visibility/save` | Works with tournaments.db | Modern | Keep as-is |

---

## ⚠️ Important Questions

1. **Are there any currently active registrations**?
   - If YES: Need migration script
   - If NO: Safe to delete legacy code

2. **Is anyone using the `/register` endpoint**?
   - If YES: Need to ensure new code works
   - If NO: Safe to refactor

3. **Should per-tournament DB code be deleted or kept for backward compatibility**?
   - Recommendation: DELETE (it's not being used)

---

## 🎯 Recommended Approach

### Option A: Complete Cleanup (Recommended)
1. Delete all per-tournament DB code
2. Delete get_tournament_db() function
3. Delete TOURNAMENTS_DIR
4. Refactor all endpoints to use tournaments.db
5. Create new tournaments.db schema
6. Update registrations to use unified DB
7. Pros: Clean, modern, maintainable
8. Cons: Requires more refactoring (~3-4 hours)

### Option B: Gradual Deprecation
1. Keep per-tournament code for now
2. Add new tournaments.db system alongside
3. Gradually migrate endpoints
4. Eventually remove old code
5. Pros: Less risky, can test gradually
6. Cons: Technical debt accumulates

---

## 📝 Summary

**Current State**: 
- ❌ Code still references tournaments/ per-tournament DBs
- ❌ ~47 places in app.py reference this legacy system
- ✅ But actual data is gone (tournaments/ is empty)
- ✅ Tournament metadata IS in admin.db (modern)

**What to do**:
1. Create clean tournaments.db schema
2. Remove all per-tournament DB code
3. Refactor endpoints to use unified DB
4. Test thoroughly

**Estimated effort**: 3-4 hours for complete cleanup

---

## Ready for Action?

Should we proceed with **Option A: Complete Cleanup**?

Or do you want to discuss the approach first?
