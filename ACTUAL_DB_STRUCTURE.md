# Actual Database Structure - /local/badmintonScrapPython

**Context**: ONLY `/local/badmintonScrapPython` project  
**Last Updated**: 2026-08-13  
**Current Status**: tournaments.db does NOT exist yet

---

## 📊 Currently Existing Databases

### 1. admin.db (40 KB)
Admin settings, credentials, and tournament visibility.

#### Tables:

**admins**
```
- id (INTEGER PRIMARY KEY)
- username (TEXT NOT NULL)
- password (TEXT)
```
Rows: 2 (admin users)

**smtp_settings**
```
- id (INTEGER PRIMARY KEY)
- smtp_host (TEXT)
- smtp_port (INTEGER)
- smtp_email (TEXT)
- smtp_password (TEXT)
- reminder_days (INTEGER)
```
Rows: 0 (no SMTP settings configured yet)

**reminders_sent**
```
- id (INTEGER PRIMARY KEY)
- tournament_db (TEXT)
- player_email (TEXT)
- sent_at (TEXT)
```
Rows: 0 (no reminders sent yet)

**bwf_tournament_visibility**
```
- id (INTEGER PRIMARY KEY)
- tournament_url (TEXT NOT NULL)
- tournament_name (TEXT)
- location (TEXT)
- date_start (TEXT)
- date_end (TEXT)
- registration_opens (TEXT)
- registration_closes (TEXT)
- cancellation_deadline (TEXT)
- competition_start (TEXT)
- competition_end (TEXT)
- visible (INTEGER) ← Which tournaments to show on homepage
- created_at (TEXT)
```
Rows: 2 (tournaments synced from Badminton Sweden)

**tournament_visibility**
```
- id (INTEGER PRIMARY KEY)
- tournament_db (TEXT NOT NULL) ← Per-tournament DB filename
- visible (INTEGER) ← Should this tournament be shown
- created_at (TEXT)
```
Rows: 0 (legacy, not used anymore)

---

### 2. players.db (140 KB)
Global registry of all badminton players.

#### Tables:

**players**
```
- id (INTEGER PRIMARY KEY)
- name (TEXT)
- profile_url (TEXT)
- club (TEXT)
- gender (TEXT)
```
Rows: 824 (players scraped from Badminton Sweden)

**Purpose**: Used for player lookup/autocomplete when registering for tournaments

---

### 3. point_rules.db (12 KB)
Badminton scoring rules and point systems.

#### Tables:

**point_rules**
```
- id (INTEGER PRIMARY KEY)
- klass (TEXT NOT NULL) ← Category: Elit, A, B, C, D
- hs_min (INTEGER) ← Herr Singel (Men's Singles) minimum points
- hs_max (INTEGER) ← Herr Singel maximum points
- ds_min (INTEGER) ← Dam Singel (Women's Singles) minimum
- ds_max (INTEGER) ← Dam Singel maximum
- hd_min (INTEGER) ← Herr Dubbel (Men's Doubles) minimum
- hd_max (INTEGER) ← Herr Dubbel maximum
- dd_min (INTEGER) ← Dam Dubbel (Women's Doubles) minimum
- dd_max (INTEGER) ← Dam Dubbel maximum
- md_min (INTEGER) ← Mixed Dubbel (Mixed Doubles) minimum
- md_max (INTEGER) ← Mixed Dubbel maximum
```
Rows: 5
```
Elit, A, B, C, D
```

---

## 📁 Missing: tournaments.db

**Status**: ❌ Does NOT exist (needs to be created)

**Planned Purpose**: Store ALL tournament data in one unified database

**Planned Tables**:

### tournaments
```
- id (INTEGER PRIMARY KEY)
- tournament_url (TEXT UNIQUE NOT NULL)
- tournament_name (TEXT NOT NULL)
- location (TEXT)
- date_start (TEXT)
- date_end (TEXT)
- registration_opens (TEXT)
- registration_closes (TEXT)
- cancellation_deadline (TEXT)
- competition_start (TEXT)
- competition_end (TEXT)
- selected_for_view (INTEGER DEFAULT 0) ← 1 = show on homepage
- created_at (TEXT)
- last_updated (TEXT)
```

**Purpose**: Store metadata for all tournaments synced from Badminton Sweden

### tournament_registrations
```
- id (INTEGER PRIMARY KEY)
- tournament_id (INTEGER NOT NULL) → tournaments.id
- player_name (TEXT NOT NULL)
- license_id (TEXT)
- club (TEXT)
- gender (TEXT)
- email (TEXT)
- phone (TEXT)
- dob (TEXT)
- age (TEXT)
- ranking (TEXT)
- singles_levels (TEXT) ← comma-separated: A,B,C
- doubles_levels (TEXT)
- mixed_levels (TEXT)
- doubles_partner (TEXT)
- mixed_partner (TEXT)
- registration_date (TEXT)
```

**Purpose**: Store player registrations for each tournament

---

## 📂 tournaments/ Directory

**Location**: `/local/badmintonScrapPython/tournaments/`

**Current Status**: Empty or has old `.db` files

**Current Issue**: ⚠️ Legacy per-tournament databases should be deleted or migrated

**Should contain**: Nothing (all data should move to unified tournaments.db)

---

## 🔄 Data Flow Currently

### On Startup
```
1. Download from Dropbox
   ├─ admin.db (tournament selections)
   ├─ players.db (player registry)
   ├─ point_rules.db (scoring rules)
   └─ tournaments/*.db (per-tournament registrations) ← BEING SYNCED

2. Initialize Flask app
```

### When User Registers for Tournament
```
1. User submits registration on tournament page
2. Saved to: tournaments/<tournament_name>.db (per-tournament DB)
   Example: tournaments/bmk_komet.db
   
3. Trigger sync (after 10 seconds)
4. Upload to Dropbox
   ├─ admin.db ✅
   ├─ players.db ✅
   ├─ point_rules.db ✅
   └─ tournaments/*.db ✅ (newly synced in this session)
```

### When Admin Selects Tournaments
```
1. Admin toggles tournament visible/hidden
2. Saved to: admin.db → bwf_tournament_visibility table
3. Trigger sync
4. Upload admin.db to Dropbox
```

---

## 🎯 Current Problems

### Problem 1: Per-Tournament Database Files
**What**: Each tournament creates its own `.db` file
- `tournaments/bmk_komet.db`
- `tournaments/some_tournament.db`
- etc.

**Why it's a problem**:
- ❌ Inconsistent architecture
- ❌ Harder to maintain
- ❌ Mix of root-level DBs + subdirectory DBs
- ❌ Per-tournament data not in unified place

**Planned fix**: Migrate all to `tournaments.db` with `tournament_registrations` table

### Problem 2: tournaments.db Missing
**Current state**: Only 3 databases exist, no unified tournaments.db

**Impact**:
- ❌ Tournament metadata stored in admin.db (wrong place)
- ❌ Registrations stored in per-tournament DBs (fragmented)
- ❌ Can't easily query "all registrations for tournament X"

**Planned fix**: Create tournaments.db with proper schema

### Problem 3: Legacy Visibility Tracking
**Current state**: Two ways to track tournament visibility
- `admin.db` → `bwf_tournament_visibility` (modern, used)
- `admin.db` → `tournament_visibility` (legacy, empty)

**Impact**: Redundant code, confusing logic

**Planned fix**: Clean up, use only one approach

---

## 📋 Current Database Count

| Database | Exists | Size | Tables | Rows |
|----------|--------|------|--------|------|
| admin.db | ✅ | 40 KB | 6 | ~4 |
| players.db | ✅ | 140 KB | 1 | 824 |
| point_rules.db | ✅ | 12 KB | 1 | 5 |
| tournaments.db | ❌ | - | - | - |
| **Per-tournament DBs** | ✅ | - | ? | ? |

---

## 🗂️ File Organization

```
/local/badmintonScrapPython/
├── admin.db                    ✅ Exists (tournament visibility)
├── players.db                  ✅ Exists (player registry)
├── point_rules.db              ✅ Exists (scoring rules)
├── tournaments.db              ❌ Missing (should exist)
└── tournaments/                ⚠️ Has legacy per-tournament DBs
    ├── bmk_komet.db            (player registrations)
    ├── other_tournament.db     (player registrations)
    └── ...
```

---

## 🔍 What Each Database Does

### admin.db
**Stores**: Administrative configuration
- Admin user credentials
- SMTP settings for emails
- Which tournaments to display on homepage
- Email reminders tracking

**Used by**: Admin interface, tournament visibility page

**Synced to Dropbox**: ✅ Yes (always)

### players.db
**Stores**: Global badminton player registry
- Player names
- Clubs
- Gender
- Profile URLs

**Used by**: Player lookup/autocomplete when registering

**Synced to Dropbox**: ✅ Yes (always)

**Source**: Scraped from Badminton Sweden website

### point_rules.db
**Stores**: Badminton scoring point systems
- Points for each category (Elit, A, B, C, D)
- Points for each discipline (Men's singles, women's singles, doubles, mixed)
- Min/max points for rankings

**Used by**: Tournament scoring calculations

**Synced to Dropbox**: ✅ Yes (always)

### Per-Tournament DBs (tournaments/*)
**Stores**: Player registrations for each tournament
- Who's registered for tournament X
- What categories they're playing
- Contact info

**Problem**: ❌ Should be consolidated into tournaments.db

**Synced to Dropbox**: ✅ Yes (newly added in this session)

### tournaments.db (MISSING)
**Should store**: All tournament data in ONE place
- Tournament metadata (dates, locations, etc.)
- All player registrations (instead of per-tournament DBs)
- Unified access to everything

**Status**: ❌ Not created yet (planned refactor)

---

## 🎓 Summary

### What We Have
- ✅ 3 working databases (admin, players, point_rules)
- ✅ Per-tournament DBs for registrations (fragmented)
- ✅ Tournament visibility in admin.db

### What We're Missing
- ❌ tournaments.db (unified tournament database)
- ❌ Consolidated registration storage

### What Needs to Change
1. Create `tournaments.db` with proper schema
2. Migrate per-tournament data into `tournament_registrations` table
3. Delete per-tournament `.db` files
4. Update app code to use new schema

---

## ❓ Questions to Discuss

1. **Should we refactor now?**
   - Pro: Cleaner architecture
   - Con: Requires migration of existing data

2. **Keep per-tournament DBs or migrate?**
   - Per-tournament: Simpler now, messy long-term
   - Unified: Clean, but requires work

3. **Do you have existing player registrations to preserve?**
   - If yes: Need migration script
   - If no: Can create clean tournaments.db

---

**Ready to discuss? What are your thoughts?** 🤔
