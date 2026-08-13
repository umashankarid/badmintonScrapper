# BadmintonScrapPython Database Schema

## Overview
All data is stored in 4 unified SQLite databases at the root level. There should be NO per-tournament databases.

```
Root level databases (ONLY):
├── players.db          - Global player registry
├── admin.db            - Admin credentials and settings
├── point_rules.db      - Badminton scoring rules
└── tournaments.db      - ALL tournament data (unified)

Directories:
└── tournaments/        - EMPTY or removed (legacy)
```

## Database Structure

### 1. players.db
Global registry of all players across all tournaments.

```sql
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT,
    license_id TEXT,
    club TEXT,
    gender TEXT,
    email TEXT,
    phone TEXT,
    dob TEXT,
    age TEXT,
    ranking TEXT,
    singles_levels TEXT,      -- comma-separated
    doubles_levels TEXT,       -- comma-separated
    mixed_levels TEXT,         -- comma-separated
    doubles_partner TEXT,
    mixed_partner TEXT
);
```

### 2. admin.db
Admin authentication and settings.

```sql
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bwf_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS smtp_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    smtp_server TEXT,
    smtp_port INTEGER,
    sender_email TEXT,
    sender_password_hash TEXT,
    use_tls INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tournament_visibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_db TEXT,
    visible INTEGER DEFAULT 0
);
```

### 3. point_rules.db
Badminton scoring rules and configuration.

```sql
CREATE TABLE IF NOT EXISTS point_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT,
    points INTEGER,
    description TEXT
);
```

### 4. tournaments.db
**ALL** tournament data unified in a single database.

#### Table: tournaments
Tournament metadata and visibility.

```sql
CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_url TEXT UNIQUE NOT NULL,
    tournament_name TEXT NOT NULL,
    location TEXT,
    date_start TEXT,
    date_end TEXT,
    registration_opens TEXT,
    registration_closes TEXT,
    cancellation_deadline TEXT,
    competition_start TEXT,
    competition_end TEXT,
    selected_for_view INTEGER DEFAULT 0,      -- 1 = visible on homepage
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### Table: tournament_registrations
Player registrations for each tournament.

```sql
CREATE TABLE IF NOT EXISTS tournament_registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    singles_level TEXT,
    doubles_level TEXT,
    mixed_level TEXT,
    doubles_partner TEXT,
    mixed_partner TEXT,
    registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);
```

#### Table: tournament_results (optional, for future)
Tournament results and rankings.

```sql
CREATE TABLE IF NOT EXISTS tournament_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    category TEXT,           -- singles, doubles_m, mixed, etc.
    position INTEGER,
    points INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
);
```

## Data Flow

### Creating a Tournament
1. **Fetch from Badminton Sweden API** → `tournaments` table
2. **Admin selects tournaments** → Set `selected_for_view = 1`
3. **Tournament appears on homepage** → Filter by `selected_for_view = 1 AND date_end >= TODAY`

### Registering a Player
1. **User enters player details** on tournament page
2. **Insert into players** table (if new)
3. **Insert into tournament_registrations** table
4. **Trigger debounce sync** → uploads `tournaments.db` to Dropbox

### On Redeploy
1. **Download tournaments.db from Dropbox**
2. **Read all tournaments and registrations**
3. **Display selected tournaments on homepage**
4. **Show existing registrations in tournament details**

## Consistency Rules

### DO ✅
- All tournament data → `tournaments.db`
- All player registrations → `tournaments.db` (tournament_registrations table)
- All global players → `players.db`
- One database per entity type

### DON'T ❌
- Create per-tournament `.db` files (`tournaments/bmk_komet.db`)
- Store tournament data in multiple databases
- Mix player registry with tournament registrations
- Duplicate data across databases

## Sync Strategy

### Files to Sync to Dropbox
```
Root only:
- players.db
- admin.db
- point_rules.db
- tournaments.db
```

### NOT to Sync
```
- tournaments/*.db (should not exist)
- Temporary files
- Cache files
```

## Migration Checklist

- [x] Create unified `tournaments.db`
- [x] Add `tournament_registrations` table for player signups
- [x] Remove per-tournament database creation
- [x] Update player registration endpoints to use `tournament_registrations`
- [x] Update sync to only handle root-level DBs
- [ ] Test end-to-end: Create tournament → Register player → Redeploy → Verify data
