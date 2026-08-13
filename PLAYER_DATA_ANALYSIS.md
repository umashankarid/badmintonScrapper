# Player Data Analysis - Where is Everything Stored?

## Current Discovery

### 1. **Global players.db** (140 KB)
**Only contains basic player information**:
- `id`
- `name`
- `profile_url`
- `club` (mostly empty)
- `gender` (mostly NULL)

**Purpose**: Used for player lookup/autocomplete  
**Rows**: 824 players  
**NOT used for registrations** ❌

---

### 2. **Per-Tournament `.db` Files** (tournaments/*.db)
**Currently EMPTY** (tournaments/ directory is empty)

**Would contain** (based on app.py code):
```sql
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT,
    license_id TEXT,           ← HERE
    club TEXT,
    gender TEXT,
    email TEXT,
    phone TEXT,
    ranking TEXT,              ← HERE
    singles_levels TEXT,
    doubles_levels TEXT,
    mixed_levels TEXT,
    doubles_partner TEXT,
    mixed_partner TEXT
)
```

**Purpose**: Store player registrations for each tournament  
**Status**: Code exists but per-tournament DBs are empty/not being created

---

### 3. **tournaments.db** (MISSING)
**Planned to contain**:
```sql
CREATE TABLE tournament_registrations (
    id INTEGER PRIMARY KEY,
    tournament_id INTEGER,
    player_name TEXT,
    license_id TEXT,           ← HERE
    club TEXT,
    gender TEXT,
    email TEXT,
    phone TEXT,
    dob TEXT,
    age TEXT,
    ranking TEXT,              ← HERE
    singles_levels TEXT,
    doubles_levels TEXT,
    mixed_levels TEXT,
    doubles_partner TEXT,
    mixed_partner TEXT,
    registration_date TEXT
)
```

**Status**: NOT created yet

---

## 📊 Summary: Where Things Are Stored

| Data | Location | Status | Size |
|------|----------|--------|------|
| Player lookup data | `players.db` | ✅ Active | 140 KB, 824 rows |
| Tournament registrations | Should be in `tournaments.db` | ❌ Missing | - |
| Player registration details (license_id, ranking) | Code expects per-tournament `.db` files | ⚠️ Code exists, no data | - |
| Admin credentials | `admin.db` | ✅ Active (just cleaned) | 40 KB |
| Scoring rules | `point_rules.db` | ✅ Active | 12 KB |

---

## ⚠️ Current Architecture Issues

### Issue 1: Fragmented Player Registration Data
- Code expects each tournament to have its own `players` table
- This table would have `license_id` and `ranking`
- **But**: per-tournament DBs are empty/not being created

### Issue 2: No Active Player Registration
- Users can't register for tournaments (or registrations are lost)
- Code to create per-tournament DBs exists but isn't being used
- No unified tournament registration system

### Issue 3: Duplicate Data
- `players.db` has basic player info (824 rows)
- Per-tournament DBs would have same player info PLUS license_id + ranking
- = Data duplication

---

## 🎯 Your Observation

You're right! The code **expects** to save `license_id` and `ranking` somewhere:

1. **In per-tournament `.db` files** - Each tournament gets a `players` table with these fields
2. **Or in app.py logic** - Functions like `get_player_ranking()` fetch this data from Badminton Sweden

But currently:
- ✅ `players.db` exists (basic info only, no license_id/ranking)
- ❌ Per-tournament DBs are empty
- ❌ `tournaments.db` doesn't exist
- ❌ No active player registration system

---

## 💡 Questions for Discussion

1. **Should we consolidate all player data in `players.db`?**
   - Add columns: `license_id`, `ranking`, `email`, `phone`, `dob`, `age`
   - Make it the single source of truth

2. **Or use `tournaments.db` for registration data?**
   - Keep `players.db` for lookup only
   - Use `tournament_registrations` table in `tournaments.db` for full player info per tournament

3. **What about the per-tournament player tables in app.py?**
   - Code exists but isn't used
   - Should we keep, update, or remove it?

4. **Do you currently have player registrations working?**
   - Are users able to register for tournaments?
   - Where is that data being stored?

---

**Bottom line**: Yes, you're seeing `license_id` and `ranking` in the code, but they're currently stored in **per-tournament player tables** (which are currently empty). We need to clarify the architecture for where registration data should live.

