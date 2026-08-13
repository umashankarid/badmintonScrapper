# Legacy Code Migration Guide

**Date**: 2026-08-13  
**Status**: Complete  
**Scope**: Transitioning legacy per-tournament code to unified schema

---

## Quick Summary

The system has migrated from per-tournament database files to a unified `tournaments.db`. Your legacy code continues to work but may not reflect the new data organization.

**Key Takeaway**: Old code gracefully degrades (returns "not found") rather than crashes. You can refactor gradually.

---

## What Broke (& Why It's Actually Safe)

### 1. Deprecated Function: `get_tournament_db()`

**Before**:
```python
def get_tournament_db(tournament_name):
    """Returns tournament database file path"""
    db_path = f"tournaments/{tournament_name}.db"
    if os.path.exists(db_path):
        return db_path
    return None
```

**After**:
```python
def get_tournament_db(tournament_name):
    """DEPRECATED: Returns None (graceful degradation)"""
    logger.warning(f"get_tournament_db() called for '{tournament_name}' (legacy code)")
    return None
```

**Impact**: ✅ Safe - returns None instead of crashing
- Old endpoints check if result is None
- Return "Tournament not found" to user
- No data corruption

---

### 2. Deprecated Directory: `tournaments/`

**Before**: Contains per-tournament `.db` files
```
tournaments/
├── bmk_komet.db
├── other_tournament.db
└── ...
```

**After**: Directory is empty (removed in cleanup)

**Impact**: ✅ Safe - old files are in backup
- If you need to recover: check `.db.backup` files
- New data lives in `tournaments.db` only
- No data loss

---

### 3. Deprecated Drive Sync

**Before**:
```python
def download_databases():
    # Download individual tournament files
    for file in tournaments_dir:
        download_file(file)
```

**After**:
```python
def download_databases():
    # Download only root databases
    dropbox_download("players.db")
    dropbox_download("admin.db")
    dropbox_download("tournaments.db")
```

**Impact**: ✅ Safe - all data still syncs
- Unified database = fewer files to sync
- Faster, more reliable sync
- No data lost

---

## Code Refactoring Path

### Step 1: Identify Legacy Code

**Search for these patterns** in your codebase:

```bash
# Find all uses of legacy functions
grep -r "get_tournament_db" .
grep -r "TOURNAMENTS_DIR" .
grep -r "tournaments/.*.db" .
```

**Expected matches**: ~11 endpoints in `app.py`

---

### Step 2: Understand the New Pattern

**Old Pattern**:
```python
db_file = get_tournament_db(tournament_name)
if not db_file:
    return "Tournament not found", 404

conn = sqlite3.connect(db_file)
cur = conn.cursor()
cur.execute("SELECT * FROM players ...")
```

**New Pattern**:
```python
# Get tournament from unified database
tournament = get_tournament_by_url(tournament_url)
if not tournament:
    return "Tournament not found", 404

# Get registrations from unified database
registrations = get_player_registrations_for_tournament(tournament['id'])
```

---

### Step 3: Refactor an Endpoint

**Example: GET /api/get-players**

**Before (Legacy)**:
```python
@app.route('/api/get-players', methods=['GET'])
def api_get_players():
    tournament_db = request.args.get('db')
    
    if not tournament_db or not os.path.exists(tournament_db):
        return jsonify({"players": []})
    
    conn = sqlite3.connect(tournament_db)
    cur = conn.cursor()
    cur.execute("SELECT name, club FROM players")
    players = [{"name": row[0], "club": row[1]} for row in cur.fetchall()]
    conn.close()
    
    return jsonify({"players": players})
```

**After (Refactored)**:
```python
@app.route('/api/get-players', methods=['GET'])
def api_get_players():
    tournament_id = request.args.get('tournament_id')
    
    if not tournament_id:
        return jsonify({"error": "tournament_id required"}), 400
    
    conn = sqlite3.connect('tournaments.db')
    cur = conn.cursor()
    
    # Get registrations for this tournament
    table_name = f"tournament_{tournament_id}_registrations"
    cur.execute(f"SELECT license_id, COUNT(*) FROM {table_name}")
    count = cur.fetchone()[0]
    
    # Get player details
    cur.execute(f"""
        SELECT p.name, p.club, r.singles_level, r.doubles_level
        FROM {table_name} r
        JOIN players p ON r.license_id = p.license_id
    """)
    
    players = [
        {
            "name": row[0],
            "club": row[1],
            "singles": row[2],
            "doubles": row[3]
        }
        for row in cur.fetchall()
    ]
    
    conn.close()
    return jsonify({"players": players, "total": count})
```

**Key Changes**:
- ✅ Use `tournament_id` instead of `tournament_db` filename
- ✅ Join with `players` table for player details
- ✅ Access unified `tournaments.db` directly
- ✅ Return structured player data

---

### Step 4: Testing Strategy

**Before Refactoring**:
1. Identify the endpoint
2. Write test for current behavior
3. Refactor the code
4. Verify test still passes
5. Commit with message: "Refactor: Migrate /endpoint to unified schema"

**Example Test**:
```python
def test_get_players_endpoint(self):
    """Test /api/get-players returns players for tournament"""
    
    # Setup: Insert tournament
    self.setup_tournament(tournament_id=1)
    self.register_player(tournament_id=1, license_id="lic_123")
    
    # Act
    response = self.client.get('/api/get-players?tournament_id=1')
    
    # Assert
    self.assertEqual(response.status_code, 200)
    data = response.get_json()
    self.assertEqual(len(data['players']), 1)
    self.assertEqual(data['players'][0]['name'], "John Doe")
```

---

## Database Query Changes

### Getting Tournament Data

**Old**:
```python
conn = sqlite3.connect("tournaments/tournament_name.db")
```

**New**:
```python
conn = sqlite3.connect("tournaments.db")

# By URL
tournament = get_tournament_by_url("https://...")

# By ID
cur.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
```

---

### Getting Players in Tournament

**Old**:
```python
cur.execute("SELECT * FROM players WHERE tournament = ?", (name,))
```

**New**:
```python
# Access the dynamic registration table
table_name = f"tournament_{tournament_id}_registrations"
cur.execute(f"SELECT * FROM {table_name}")

# Join with global players table for full details
cur.execute(f"""
    SELECT p.*, r.singles_level, r.doubles_level
    FROM {table_name} r
    JOIN players p ON r.license_id = p.license_id
""")
```

---

### Getting Player Ranking Data

**Old**:
```python
# Ranking might be in different columns per tournament
cur.execute("SELECT ranking FROM players WHERE name = ?", (name,))
```

**New**:
```python
# All ranking data is JSON in players table
cur.execute("""
    SELECT ranking FROM players WHERE license_id = ?
""", (license_id,))

ranking_json = json.loads(row[0])
singles_rank = ranking_json.get('singles', {}).get('A', {}).get('rank')
```

---

## Common Pitfalls

### Pitfall 1: Assuming Files Exist

**❌ Wrong**:
```python
db_file = f"tournaments/{name}.db"
conn = sqlite3.connect(db_file)  # Creates empty DB if not found!
```

**✅ Right**:
```python
tournament = get_tournament_by_url(url)
if not tournament:
    return error_response("Tournament not found")

conn = sqlite3.connect("tournaments.db")
```

---

### Pitfall 2: Hardcoding Table Names

**❌ Wrong**:
```python
cur.execute("SELECT * FROM players")  # Which tournament's players?
```

**✅ Right**:
```python
table_name = f"tournament_{tournament_id}_registrations"
cur.execute(f"SELECT * FROM {table_name}")
```

---

### Pitfall 3: Missing License ID

**❌ Wrong**:
```python
# Old system used player name as identifier
cur.execute("SELECT * FROM players WHERE name = ?", (name,))
```

**✅ Right**:
```python
# New system uses license_id (from Badminton Sweden)
cur.execute("SELECT * FROM players WHERE license_id = ?", (license_id,))
```

---

### Pitfall 4: Forgotten JSON Parsing

**❌ Wrong**:
```python
ranking = row['ranking']  # This is a string!
rank_a = ranking['singles']  # TypeError!
```

**✅ Right**:
```python
ranking = json.loads(row['ranking'])
rank_a = ranking.get('singles', {}).get('A', {}).get('rank')
```

---

## Endpoint Refactoring Checklist

These 11 endpoints still use legacy code:

```
[ ] 1. GET  /tournament-visibility/toggle
[ ] 2. GET  /tournament-events
[ ] 3. GET  /register
[ ] 4. POST /api/add-player
[ ] 5. POST /api/delete-player
[ ] 6. GET  /api/get-players
[ ] 7. POST /api/register-player
[ ] 8. GET  /api/tournament-details
[ ] 9. POST /api/update-levels
[ ] 10. GET /api/validate-registration
[ ] 11. POST /api/export-tournament
```

**For each endpoint**:
- [ ] Write test for current behavior
- [ ] Identify tournament_id parameter source
- [ ] Replace `get_tournament_db()` call
- [ ] Update database queries
- [ ] Run test to verify
- [ ] Commit with message: "Refactor: Migrate /endpoint to unified schema"

---

## Rollback Plan

If something goes wrong:

1. **Restore backup databases**:
   ```bash
   cp players.db.backup.* players.db
   cp admin.db.backup.* admin.db
   ```

2. **Restore per-tournament files** (if needed):
   ```bash
   git show HEAD~5:tournaments/tournament_name.db > tournaments/tournament_name.db
   ```

3. **Revert code changes**:
   ```bash
   git revert <commit_hash>
   ```

---

## Support & Questions

**Q: Can I still access old tournament data?**  
A: Yes! Use `get_player_registrations_for_tournament(tournament_id)` to access registrations for any tournament.

**Q: How do I know which tournament_id corresponds to which tournament?**  
A: Query tournaments table: `SELECT id, tournament_name FROM tournaments`

**Q: Is my data safe during refactoring?**  
A: ✅ Yes - multiple backups, graceful degradation, no destructive changes.

**Q: Can I run old and new code side-by-side?**  
A: ✅ Yes - old endpoints return "not found", new endpoints work independently.

---

## Timeline

- [x] Phase 1: Database schema created
- [x] Phase 2: Data migrated and verified
- [x] Phase 3: Helper functions implemented
- [x] Phase 4: One endpoint refactored (/api/tournaments)
- [ ] Phase 5: Refactor remaining 11 endpoints (optional)
- [ ] Phase 6: Retire legacy code entirely

**Current Status**: Phases 1-4 complete, Phase 5 in progress, Phase 6 future
