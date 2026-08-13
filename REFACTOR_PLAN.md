# Refactor Plan: Unified Database Architecture

## Current State (Broken ❌)
- Per-tournament databases: `tournaments/bmk_komet.db`, `tournaments/some_tournament.db`
- Each tournament has its own players table with registrations
- Sync code updated to sync `tournaments/*.db` files
- But this contradicts the earlier refactor goal

## Target State (Desired ✅)
- Single `tournaments.db` with:
  - `tournaments` table (tournament metadata)
  - `tournament_registrations` table (player signups)
- Global `players.db` (if needed for global player registry)
- Clean Dropbox sync (only 4 root DBs)

## Refactor Steps

### Phase 1: Add tournament_registrations table to tournaments.db
- [ ] Update `init_tournaments_db()` to create `tournament_registrations` table
- [ ] Add foreign key relationships

### Phase 2: Update Player Registration Endpoints
- [ ] Update `add_player()` endpoint to:
  - Accept `tournament_id` instead of `db_file`
  - Insert into `tournament_registrations` table
  - Still update global `players.db`
- [ ] Update `delete_player()` similarly
- [ ] Update `get_tournament_players()` to read from `tournament_registrations`

### Phase 3: Update Data Migration
- [ ] Create migration script to import existing per-tournament DBs into `tournaments.db`
- [ ] Test migration preserves all data

### Phase 4: Clean Up Old Code
- [ ] Remove per-tournament DB creation code
- [ ] Remove `tournaments/` directory handling
- [ ] Update sync to only handle 4 root DBs
- [ ] Remove `TOURNAMENTS_DIR` and `get_tournament_db()` function

### Phase 5: Test End-to-End
- [ ] Register player in tournament
- [ ] Verify stored in `tournaments.db`
- [ ] Redeploy
- [ ] Verify data persists

## Files to Modify
1. `app.py` - Remove per-tournament DB logic, update endpoints
2. `drive_sync.py` - Remove `tournaments/` directory handling
3. `tournaments.db` - Add `tournament_registrations` table
4. Remove `tournaments/` directory

## Risk Assessment
- **Medium Risk**: Need to migrate existing per-tournament data
- **Mitigation**: Keep backup of all `tournaments/*.db` files
- **Rollback**: Easy if we keep git history

## Timeline
- ~2-3 hours for full refactor + testing
