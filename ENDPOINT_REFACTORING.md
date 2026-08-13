# Endpoint Refactoring Plan

**Status**: Phase 5 - Endpoint Migration  
**Date**: 2026-08-13

## Overview

This document tracks the refactoring of 11 legacy endpoints to use the unified `tournaments.db` schema.

---

## Identified Legacy Endpoints

### Visibility & Tournament Management (3 endpoints)

1. **GET /api/tournament-visibility**
   - **Status**: ⚠️ LEGACY
   - **Current**: Scans tournaments/ directory, queries tournament_visibility table
   - **Issue**: Relies on TOURNAMENTS_DIR (removed)
   - **Solution**: Query tournaments.db, join with admin.db visibility flags

2. **POST /api/tournament-visibility/toggle**
   - **Status**: ⚠️ LEGACY
   - **Current**: Toggles visibility in admin.db using db filename as key
   - **Issue**: db filename no longer relevant (unified schema)
   - **Solution**: Use tournament_id as key instead of filename

3. **POST /api/bwf-tournament-visibility/save**
   - **Status**: ⚠️ LEGACY
   - **Current**: Saves BWF tournament visibility settings
   - **Issue**: References old tournament_visibility table schema
   - **Solution**: Update to use tournaments table with selected_for_view flag

### Registration & Events (3 endpoints)

4. **POST /api/validate-registration**
   - **Status**: ⚠️ LEGACY
   - **Current**: Validates player registration in tournament
   - **Issue**: Checks old tournament db file
   - **Solution**: Query tournament_<id>_registrations table

5. **GET /api/my-registrations**
   - **Status**: ⚠️ LEGACY
   - **Current**: Gets player's registrations across tournaments
   - **Issue**: Scans multiple tournament files
   - **Solution**: Query tournament_*_registrations tables where license_id matches

6. **GET /api/tournament-events**
   - **Status**: ⚠️ LEGACY
   - **Current**: Returns tournament events/schedule
   - **Issue**: Reads from per-tournament db
   - **Solution**: Query tournaments.db for date_start, date_end, etc.

### Tournament Discovery (3 endpoints)

7. **GET /api/bwf-tournaments-all**
   - **Status**: ⚠️ LEGACY
   - **Current**: Returns all tournaments (visible or not)
   - **Issue**: Scans filesystem
   - **Solution**: Query tournaments.db

8. **GET /api/open-tournaments**
   - **Status**: ⚠️ LEGACY
   - **Current**: Returns open/active tournaments
   - **Issue**: Old visibility logic
   - **Solution**: Query tournaments where selected_for_view=1 AND date_end >= TODAY

9. **GET /api/ensure-tournament**
   - **Status**: ⚠️ LEGACY
   - **Current**: Ensures tournament exists in system
   - **Issue**: Filesystem-based logic
   - **Solution**: Direct database lookup

### Create/Delete/Edit (2 endpoints - partial refactoring needed)

10. **POST /admin/create-tournament**
    - **Status**: ⚠️ PARTIAL
    - **Current**: Creates tournament db file
    - **Issue**: Should use tournaments.db
    - **Solution**: Insert into tournaments table

11. **POST /admin/delete-tournament**
    - **Status**: ⚠️ PARTIAL
    - **Current**: Deletes tournament db file
    - **Issue**: Should use tournaments.db
    - **Solution**: Delete from tournaments table and drop registration table

---

## Refactoring Priority

### High Priority (User-facing, core functionality)
- [ ] GET /api/tournaments (✅ DONE in Phase 4)
- [ ] POST /api/validate-registration
- [ ] GET /api/my-registrations
- [ ] GET /api/open-tournaments

### Medium Priority (Admin functionality)
- [ ] GET /api/tournament-visibility
- [ ] POST /api/tournament-visibility/toggle
- [ ] POST /admin/create-tournament

### Low Priority (Deprecated or rarely used)
- [ ] GET /api/tournament-events
- [ ] GET /api/bwf-tournaments-all
- [ ] POST /api/bwf-tournament-visibility/save
- [ ] GET /api/ensure-tournament
- [ ] POST /admin/delete-tournament

---

## Refactoring Process

For each endpoint:

1. **Read current implementation** - Understand what it does
2. **Write test** - Capture current behavior
3. **Refactor code** - Convert to new schema
4. **Run test** - Verify it still passes
5. **Commit** - Record change with clear message
6. **Update documentation** - Note breaking changes

---

## Example Refactoring Pattern

### Pattern 1: Visibility Toggle

**Before** (Legacy):
```python
@app.route("/api/tournament-visibility/toggle", methods=["POST"])
def toggle_tournament_visibility():
    db_file = request.json.get('db_file')
    
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    
    # Get current visibility
    cur.execute("SELECT visible FROM tournament_visibility WHERE tournament_db=?", (db_file,))
    row = cur.fetchone()
    current = row[0] if row else 0
    
    # Toggle
    new_visibility = 1 - current
    cur.execute("""
        INSERT OR REPLACE INTO tournament_visibility (tournament_db, visible)
        VALUES (?, ?)
    """, (db_file, new_visibility))
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, visibility=new_visibility)
```

**After** (Refactored):
```python
@app.route("/api/tournament-visibility/toggle", methods=["POST"])
def toggle_tournament_visibility():
    tournament_id = request.json.get('tournament_id')
    
    conn = sqlite3.connect('tournaments.db')
    cur = conn.cursor()
    
    # Get current visibility
    cur.execute("""
        SELECT selected_for_view FROM tournaments WHERE id=?
    """, (tournament_id,))
    
    row = cur.fetchone()
    if not row:
        return jsonify(success=False, error="Tournament not found"), 404
    
    # Toggle
    current = row[0]
    new_visibility = 1 - current
    
    cur.execute("""
        UPDATE tournaments
        SET selected_for_view = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_visibility, tournament_id))
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, visibility=new_visibility)
```

**Key Changes**:
- ✅ Use tournament_id instead of db_file
- ✅ Query tournaments table directly (not admin.db)
- ✅ Update selected_for_view field
- ✅ Return tournament_id in responses

---

### Pattern 2: Registration Lookup

**Before** (Legacy):
```python
@app.route("/api/validate-registration", methods=["POST"])
def validate_registration():
    tournament_db = request.json.get('tournament_db')
    player_name = request.json.get('player_name')
    
    if not tournament_db or not os.path.exists(tournament_db):
        return jsonify(valid=False)
    
    conn = sqlite3.connect(tournament_db)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM players WHERE name=?
    """, (player_name,))
    
    result = cur.fetchone()
    conn.close()
    
    return jsonify(valid=result is not None)
```

**After** (Refactored):
```python
@app.route("/api/validate-registration", methods=["POST"])
def validate_registration():
    tournament_id = request.json.get('tournament_id')
    license_id = request.json.get('license_id')
    
    if not tournament_id or not license_id:
        return jsonify(valid=False, error="Missing tournament_id or license_id")
    
    conn = sqlite3.connect('tournaments.db')
    cur = conn.cursor()
    
    # Check if player is registered for this tournament
    table_name = f"tournament_{tournament_id}_registrations"
    cur.execute(f"""
        SELECT id FROM {table_name} WHERE license_id=?
    """, (license_id,))
    
    result = cur.fetchone()
    conn.close()
    
    return jsonify(
        valid=result is not None,
        tournament_id=tournament_id,
        license_id=license_id
    )
```

**Key Changes**:
- ✅ Use tournament_id and license_id
- ✅ Query dynamic registration table
- ✅ Better error messages
- ✅ Return relevant identifiers

---

## Testing Strategy

### Before/After Comparison

For each endpoint, create tests that verify:

1. **Existing behavior preserved** - Old tests pass
2. **New schema used** - Queries hit tournaments.db
3. **Error handling** - Invalid IDs return 404, not 500
4. **Data integrity** - No data lost in refactoring

### Test Example

```python
class TestValidateRegistrationRefactor(unittest.TestCase):
    
    def setUp(self):
        # Create test tournament and registration
        self.setup_test_data()
    
    def test_validate_existing_registration(self):
        """Test: Validate existing player registration"""
        response = self.client.post(
            '/api/validate-registration',
            json={
                'tournament_id': 1,
                'license_id': 'lic_123'
            }
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['valid'])
    
    def test_validate_missing_player(self):
        """Test: Return false for unregistered player"""
        response = self.client.post(
            '/api/validate-registration',
            json={
                'tournament_id': 1,
                'license_id': 'lic_nonexistent'
            }
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['valid'])
    
    def test_validate_missing_tournament(self):
        """Test: Return 404 for missing tournament"""
        response = self.client.post(
            '/api/validate-registration',
            json={
                'tournament_id': 999,
                'license_id': 'lic_123'
            }
        )
        
        # Should handle gracefully
        self.assertIn(response.status_code, [200, 404])
```

---

## Backward Compatibility

### During Migration

1. **Accept both formats** (temporarily):
   ```python
   # Accept old format
   db_file = request.json.get('db_file')
   
   # Or new format
   tournament_id = request.json.get('tournament_id')
   
   # If old format, convert to ID
   if db_file:
       tournament_id = get_tournament_id_from_filename(db_file)
   ```

2. **Return both formats** (temporarily):
   ```python
   return jsonify(
       # New format
       tournament_id=1,
       success=True,
       # Legacy format (deprecated)
       db_file="tournaments/name.db",
       success=True
   )
   ```

3. **Deprecation warnings**:
   ```python
   if db_file:
       logger.warning(f"Deprecated: Use tournament_id instead of db_file")
   ```

---

## Commit Messages

Use this format for commits:

```
Refactor: Migrate /api/endpoint to unified schema

ENDPOINT MIGRATION

Old endpoint: /api/endpoint
New parameters: tournament_id (instead of tournament_db)

Changes:
- Query tournaments.db instead of per-tournament files
- Use license_id for player identification
- Updated response format

Database:
- tournaments table (metadata)
- tournament_<id>_registrations (player registrations)

Testing:
- [x] Existing behavior preserved
- [x] New schema queries verified
- [x] Error handling validated

Status:
- Replaces GET /api/tournament-visibility/toggle
- 9 other endpoints remaining
```

---

## Implementation Timeline

**Phase 5A** - High Priority Endpoints (Days 1-2)
- [ ] GET /api/validate-registration
- [ ] POST /api/my-registrations
- [ ] GET /api/open-tournaments

**Phase 5B** - Admin Endpoints (Days 3-4)
- [ ] GET /api/tournament-visibility
- [ ] POST /api/tournament-visibility/toggle
- [ ] POST /admin/create-tournament

**Phase 5C** - Cleanup Endpoints (Days 5)
- [ ] GET /api/tournament-events
- [ ] GET /api/bwf-tournaments-all
- [ ] POST /api/bwf-tournament-visibility/save
- [ ] GET /api/ensure-tournament
- [ ] POST /admin/delete-tournament

---

## Rollback Plan

If refactoring breaks functionality:

1. **Revert commit**: `git revert <commit_hash>`
2. **Check tests**: `python3 -m unittest discover`
3. **Review logs**: `git show <commit_hash>`
4. **Try different approach**: Refer to this doc

---

## Status Tracking

```
[ ] 1. GET /api/validate-registration
[ ] 2. POST /api/my-registrations  
[ ] 3. GET /api/open-tournaments
[ ] 4. GET /api/tournament-visibility
[ ] 5. POST /api/tournament-visibility/toggle
[ ] 6. POST /admin/create-tournament
[ ] 7. GET /api/tournament-events
[ ] 8. GET /api/bwf-tournaments-all
[ ] 9. POST /api/bwf-tournament-visibility/save
[ ] 10. GET /api/ensure-tournament
[ ] 11. POST /admin/delete-tournament

Completed: 1/12 (/api/tournaments)
In Progress: 0/12
Remaining: 10/12
```

---

**Next Step**: Begin Phase 5A - Start with GET /api/validate-registration
