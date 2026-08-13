# Players.db Refactor - Complete Plan

## ✅ APPROVED DESIGN

### 1. **Players.db Schema (NEW)**

```sql
CREATE TABLE players (
    license_id TEXT PRIMARY KEY,      -- Unique identifier from Badminton Sweden
    name TEXT NOT NULL,
    profile_url TEXT,
    club TEXT,
    gender TEXT,
    email TEXT,
    phone TEXT,
    dob TEXT,
    age TEXT,
    ranking TEXT,                     -- JSON format (see below)
    last_updated TIMESTAMP,
    last_scraped TIMESTAMP
)
```

**Ranking JSON Format**:
```json
{
  "singles": {
    "A": {"rank": 5, "points": 1250},
    "B": {"rank": null, "points": 0}
  },
  "doubles": {
    "men": {"rank": 12, "points": 800},
    "women": {"rank": null, "points": 0},
    "mixed": {"rank": 8, "points": 950}
  }
}
```

---

### 2. **Update Strategy**

#### **On Application Startup**
```
1. Load players.db (if exists)
2. Scrape ALL players from Badminton Sweden
3. Insert/update into players.db
4. Status: ✅ All 824+ players loaded with current rankings
```

#### **On User Login**
```
1. Identify user by license_id
2. Scrape their data from Badminton Sweden
3. Compare with existing players.db entry
4. Update if ANY field changed:
   - ranking
   - club
   - email
   - phone
   - age
5. Update last_updated timestamp
6. Status: ✅ User's data is current
```

#### **On Player Registration for Tournament**
```
1. Query players.db by license_id
2. Reference the data (don't duplicate)
3. Store registration in tournaments.db → tournament_<id> table
4. Status: ✅ Single source of truth (players.db)
```

---

### 3. **Tournaments.db Schema (NEW)**

#### **Main tables in tournaments.db**:

```sql
-- Tournament metadata
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

-- Registration for tournament (one table per tournament created dynamically)
CREATE TABLE tournament_<id>_registrations (
    id INTEGER PRIMARY KEY,
    license_id TEXT NOT NULL,      -- References players.license_id
    singles_level TEXT,
    doubles_level TEXT,
    mixed_level TEXT,
    doubles_partner TEXT,
    mixed_partner TEXT,
    registration_date TIMESTAMP,
    FOREIGN KEY (license_id) REFERENCES players(license_id)
)
```

**Dynamic table naming**:
- Tournament ID 1: `tournament_1_registrations`
- Tournament ID 2: `tournament_2_registrations`
- etc.

---

### 4. **Data Flow**

#### **Startup Flow**
```
App Starts
  ↓
Load players.db (if exists)
  ↓
Call: scrape_all_players_from_badminton_sweden()
  ↓
Insert/Update into players.db
  ↓
Load tournaments from Badminton Sweden
  ↓
Store in tournaments.db → tournaments table
  ↓
✅ Ready for use
```

#### **User Login Flow**
```
User logs in with license_id
  ↓
Call: scrape_player_data(license_id)
  ↓
Get fresh data from Badminton Sweden
  ↓
Compare with players.db
  ↓
If changed: UPDATE players
  ↓
Set last_updated = NOW()
  ↓
✅ User's data synced
```

#### **Player Registration Flow**
```
User registers for tournament X
  ↓
Get license_id from user
  ↓
Query players.db (read-only, just reference)
  ↓
Insert into tournament_X_registrations table
  ↓
Store: license_id, levels, partners, registration_date
  ↓
✅ Registration stored
```

---

### 5. **Key Design Decisions**

| Decision | Why |
|----------|-----|
| license_id as PK | Stable unique identifier from Badminton Sweden |
| Ranking as JSON | Flexible for different categories, searchable |
| Scrape on startup | Bulk load all players once, fast |
| Scrape on login | Keep individual player data fresh |
| Reference players.db | Single source of truth, no duplication |
| Separate tournament registration tables | Organized by tournament, easy queries |

---

### 6. **Files to Create/Modify**

**Create**:
- `players_scraper.py` - Scrape functions for Badminton Sweden
- `migrate_players_db.py` - Migration script from old to new schema

**Modify**:
- `app.py` - Update login, registration, player lookup logic
- `drive_sync.py` - Include new schema in sync

**Already exists**:
- `scraper.py` - Has some scraping logic (can reuse)

---

### 7. **Implementation Phases**

**Phase 1: Create new players.db schema**
- Rename current players table
- Create new players table with all fields
- Migrate existing 824 players

**Phase 2: Implement scraping**
- Create `players_scraper.py` module
- Implement `scrape_all_players()`
- Implement `scrape_player_by_license_id()`

**Phase 3: Integrate with app**
- Call `scrape_all_players()` on startup
- Call `scrape_player_by_license_id()` on login
- Update registration flow

**Phase 4: Update tournaments.db**
- Create `tournament_registrations` tables dynamically
- Update registration endpoints

---

### 8. **Sync to Dropbox**

**Files synced** (already working):
- ✅ players.db
- ✅ admin.db
- ✅ point_rules.db
- ✅ tournaments.db (when created)

**Result**: All player data always backed up, recoverable on redeploy

---

## ✅ READY TO IMPLEMENT

All decisions approved. Ready to start coding:

1. ✅ New players.db schema (license_id as PK)
2. ✅ Scrape all players on startup
3. ✅ Scrape individual player on login
4. ✅ Update registrations to reference players.db
5. ✅ Store registrations in tournaments.db per-tournament tables

Let's begin! 🚀
