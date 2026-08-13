# Unit Tests - BadmintonScrapPython

## Overview
This document describes the unit tests for BadmintonScrapPython. These tests verify critical functionality and ensure that new changes don't break existing behavior.

## Running Tests

### Run all tests
```bash
python3 -m unittest test_badminton -v
```

### Run specific test class
```bash
python3 -m unittest test_badminton.TestTournamentRegistrations -v
```

### Run specific test
```bash
python3 -m unittest test_badminton.TestTournamentVisibility.test_toggle_tournament_visibility -v
```

### Run with pytest (after pip install pytest)
```bash
python3 -m pytest test_badminton.py -v
```

## Test Coverage

### TestDatabaseSchema (2 tests)
Tests database structure and schema integrity.

- **test_tournaments_db_schema**: Verifies tournaments.db has required tables and columns
- **test_tournament_insertion**: Tests inserting a tournament and retrieving it

**Validates**: Database initialization, schema consistency

### TestTournamentRegistrations (3 tests)
Tests player registration functionality for tournaments.

- **test_register_player_in_tournament**: Register single player for tournament
- **test_multiple_registrations_for_tournament**: Register multiple players for same tournament
- **test_delete_registration**: Delete a player registration

**Validates**: Core tournament registration flow, data persistence

### TestTournamentVisibility (3 tests)
Tests tournament selection and visibility features.

- **test_get_selected_tournaments**: Filter only selected tournaments
- **test_toggle_tournament_visibility**: Toggle tournament visible/hidden state
- **test_filter_by_end_date**: Filter active tournaments by end date

**Validates**: Tournament selection logic, data filtering, expiration handling

### TestDropboxSync (2 tests)
Tests Dropbox synchronization logic.

- **test_file_exists_check**: Verify file existence checking
- **test_sync_files_list**: Verify only root-level DBs are synced (no per-tournament DBs)

**Validates**: Sync file list, clean architecture (unified DB only)

### TestDataIntegrity (2 tests)
Tests database constraints and data consistency.

- **test_foreign_key_constraint**: Verify foreign key constraints
- **test_unique_constraint**: Verify unique constraints on tournament_url

**Validates**: Database integrity, constraint enforcement

## Test Results

All 12 tests pass:
```
test_foreign_key_constraint ............................ ok
test_unique_constraint .................................. ok
test_tournament_insertion ............................... ok
test_tournaments_db_schema .............................. ok
test_file_exists_check .................................. ok
test_sync_files_list .................................... ok
test_delete_registration ................................ ok
test_multiple_registrations_for_tournament ............. ok
test_register_player_in_tournament ..................... ok
test_filter_by_end_date ................................. ok
test_get_selected_tournaments ........................... ok
test_toggle_tournament_visibility ....................... ok

Ran 12 tests in 0.093s
OK
```

## Before Making Changes

**Important**: Run tests before and after any code changes:

```bash
# Before changes
python3 -m unittest test_badminton -v

# Make your changes...

# After changes - must still pass
python3 -m unittest test_badminton -v
```

If tests fail, fix the code or update the tests if the behavior changed intentionally.

## Critical Paths Tested

These are the core behaviors that must work:

✅ Tournament metadata storage and retrieval  
✅ Player registration for tournaments  
✅ Tournament visibility/selection toggling  
✅ Active tournament filtering (by end date)  
✅ Multiple player registrations per tournament  
✅ Tournament deletion  
✅ Foreign key relationships  
✅ Unique constraint enforcement  
✅ Sync files list (only root DBs, no per-tournament DBs)

## Adding New Tests

When adding new features, add corresponding tests:

```python
class TestNewFeature(unittest.TestCase):
    def setUp(self):
        # Initialize test data
        pass
    
    def tearDown(self):
        # Clean up
        pass
    
    def test_feature_behavior(self):
        # Test the feature
        self.assertEqual(result, expected)
```

Run your new test:
```bash
python3 -m unittest test_badminton.TestNewFeature -v
```

## Continuous Integration

These tests should be run:
- Before every commit (pre-commit hook)
- In CI/CD pipeline before deployment
- After any database schema changes
- Before any refactoring

## Known Limitations

- Tests use in-memory SQLite databases (not mocked Dropbox)
- No HTTP request testing (Badminton Sweden API)
- No authentication testing (admin endpoints)
- Mock user sessions not tested

These can be added in future iterations.
