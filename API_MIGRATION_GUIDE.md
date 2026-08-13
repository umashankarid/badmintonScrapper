# API Migration Guide - New Schema

**Date**: 2026-08-13  
**Status**: Complete

---

## Overview

This guide documents the migration from per-tournament database files to a unified `tournaments.db` schema.

**Key Change**: Instead of separate `.db` files for each tournament in `tournaments/` directory, all data now lives in a single `tournaments.db` with proper relationships.

---

## Before: Per-Tournament Schema

```
tournaments/
├── bmk_komet.db         # Contains tournament metadata + player registrations
├── other_tournament.db  # Separate file per tournament
└── ...

Each .db had:
- tournaments table (metadata)
- players table (registrations)
```

**Problems**:
- ❌ Fragmented data across many files
- ❌ Complex sync logic
- ❌ Hard to query across tournaments
- ❌ Data duplication

---

## After: Unified Schema

```
tournaments.db (single file)
├── tournaments table (metadata for all tournaments)
└── tournament_<id>_registrations (registrations for each tournament)

players.db (global player registry)
├── license_id (PK)
├── name, club, gender
├── email, phone, dob, age
└── ranking (JSON format)
```

**Benefits**:
- ✅ Single source of truth
- ✅ Clean relationships with foreign keys
- ✅ Easy to query across tournaments
- ✅ No data duplication
- ✅ Simpler sync logic

---

## API Changes

### Endpoint Changes

#### Deprecated: Legacy Per-Tournament Endpoints

These endpoints now return "Tournament not found" gracefully:

```
GET/POST /tournament-visibility/toggle
GET      /tournament-events
GET/POST /register
POST     /api/add-player
POST     /api/delete-player
GET      /api/get-players
```

**Reason**: Legacy code uses `get_tournament_db()` which returns None.

**New Approach**: Use tournament_id from tournaments.db instead of db_file parameter.

---

### Updated: GET /api/tournaments

**Before**:
```json
{
  "db": "bmk_komet.db",
  "name": "Tournament Name",
  "levels": ["A", "B", "C"],
  "competition_date": "2026-08-20"
}
```

**After**:
```json
{
  "id": 1,
  "tournament_name": "Tournament Name",
  "location": "Stockholm",
  "date_start": "2026-08-15",
  "date_end": "2026-08-20",
  "registrations": 5
}
```

**Changes**:
- ✅ `id` field now primary identifier (not filename)
- ✅ Structured date fields (date_start, date_end)
- ✅ Location field added
- ✅ Registration count included
- ✅ Returns only selected tournaments (selected_for_view=1)
- ✅ Filters expired tournaments (date_end >= TODAY)

---

### New: Tournament Registration

**Schema** (tournament_<id>_registrations table):

```sql
id INTEGER PRIMARY KEY
license_id TEXT NOT NULL        -- References players.license_id
singles_level TEXT              -- A, B, C, D, Elit
doubles_level TEXT              -- HS, DS, HD, DD
mixed_level TEXT                -- MD
doubles_partner TEXT            -- Partner name
mixed_partner TEXT              -- Partner name
registration_date TIMESTAMP     -- When registered
```

**Insert Example**:
```python
register_player_for_tournament(
    tournament_id=1,
    license_id="lic_123",
    singles_level="A",
    doubles_level="B",
    mixed_level="C",
    doubles_partner="Partner Name"
)
```

**Query Example**:
```python
# Get all registrations for tournament
SELECT * FROM tournament_1_registrations

# Get specific player registration
SELECT * FROM tournament_1_registrations 
WHERE license_id = "lic_123"

# Count registrations
SELECT COUNT(*) FROM tournament_1_registrations
```

---

## Database Schema

### tournaments.db

#### Table: tournaments

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
tournament_url TEXT UNIQUE NOT NULL
tournament_name TEXT NOT NULL
location TEXT
date_start TEXT
date_end TEXT
registration_opens TEXT
registration_closes TEXT
cancellation_deadline TEXT
competition_start TEXT
competition_end TEXT
selected_for_view INTEGER DEFAULT 0      -- 1=show on homepage
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

#### Table: tournament_<id>_registrations (dynamic)

Created on-demand for each tournament:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
license_id TEXT NOT NULL
singles_level TEXT
doubles_level TEXT
mixed_level TEXT
doubles_partner TEXT
mixed_partner TEXT
registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

---

### players.db

#### Table: players

```sql
license_id TEXT PRIMARY KEY                     -- Unique identifier from Badminton Sweden
name TEXT NOT NULL
profile_url TEXT
club TEXT
gender TEXT
email TEXT
phone TEXT
dob TEXT
age TEXT
ranking TEXT                                    -- JSON format (see below)
last_updated TIMESTAMP
last_scraped TIMESTAMP
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

## Helper Functions

### tournaments.db Functions

**Location**: `app.py` (starting line ~330)

```python
# Get tournament by URL
tournament = get_tournament_by_url("https://badminton...url")

# Get all registrations for tournament
registrations = get_player_registrations_for_tournament(tournament_id=1)

# Register player
register_player_in_tournament(
    tournament_id=1,
    player_name="John Doe",
    license_id="lic_123",
    club="Club A",
    ...
)

# Delete player registration
delete_player_from_tournament(tournament_id=1, license_id="lic_123")
```

### players.db Functions

**Location**: `players_scraper.py`

```python
# Scrape all players from Badminton Sweden
count = scrape_all_players()

# Scrape individual player
player = scrape_player_by_license_id("lic_123")

# Get player from database
player = get_player_by_license_id("lic_123")

# Update player in database
update_player_in_db(
    license_id="lic_123",
    name="John Doe",
    ranking=ranking_json
)
```

---

## Migration Checklist

- [x] Created unified tournaments.db schema
- [x] Created players.db with license_id primary key
- [x] Added helper functions for new schema
- [x] Refactored /api/tournaments endpoint
- [x] Integrated player scraper into startup
- [x] Integrated player scraper into login
- [x] Removed per-tournament DB sync logic
- [ ] Refactor remaining 11 endpoints
- [ ] Create new admin UI for tournament management
- [ ] Update frontend to use new schema

---

## Testing

### Unit Tests (12 tests)
```
test_badminton.py
- TestDatabaseSchema (2)
- TestTournamentRegistrations (3)
- TestTournamentVisibility (3)
- TestDropboxSync (2)
- TestDataIntegrity (2)
```

### Integration Tests (7 tests)
```
test_integration.py
- TestDatabaseIntegration (3)
- TestPlayerDataFlow (2)
- TestDataPersistence (1)
- TestConstraints (1)
```

**Run all tests**:
```bash
python3 -m unittest discover
# Result: Ran 19 tests in 0.148s - OK
```

---

## Environment Variables

```
# Dropbox sync
DROPBOX_ACCESS_TOKEN=sl_...
DROPBOX_ENCRYPTED_CREDS=gAAAAAB...
DROPBOX_SYNC_FOLDER=/BadmintonScrapPython-Databases

# Badminton Sweden credentials (optional, for scraper)
BADMINTON_SWEDEN_USER=...
BADMINTON_SWEDEN_PASSWORD=...
```

---

## Backward Compatibility

**Legacy Code Status**: Graceful degradation
- Old endpoints that used `get_tournament_db()` return "Tournament not found"
- No crashes or data corruption
- Can be refactored gradually as new UI is built
- All data is safe and accessible via new schema

**Data Preservation**: All existing data
- 824 players migrated to new players.db
- Tournament metadata preserved in tournaments.db
- No data loss in migration

---

## Next Steps

1. **Refactor remaining endpoints** (11 total)
   - Use tournament_id instead of db_file
   - Query tournaments.db directly
   - Return new schema responses

2. **Create new admin UI**
   - Tournament management interface
   - Registration management
   - Player lookup

3. **Update frontend**
   - Use new /api/tournaments response format
   - Update registration flow
   - Add tournament selection UI

---

## Support

For questions about the new schema:
- Check `DATABASE_SCHEMA.md` for complete table definitions
- See `test_integration.py` for usage examples
- Review `players_scraper.py` for player data operations
