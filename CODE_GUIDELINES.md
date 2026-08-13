# Code Guidelines for badmintonScrapPython

**Effective Date**: 2026-08-13  
**Version**: 1.0  
**Status**: Active - All Work Must Follow These Guidelines

---

## Table of Contents
1. [Testing Requirements](#testing-requirements)
2. [Logging Requirements](#logging-requirements)
3. [Change Documentation](#change-documentation)
4. [Project Focus](#project-focus)
5. [Git Workflow](#git-workflow)
6. [Code Review Process](#code-review-process)

---

## Testing Requirements

### Mandatory for All New Code

**Rule 1: Unit Test First**
- ✅ Write unit test BEFORE implementing feature
- ✅ Every new function must have at least one test
- ✅ Every new endpoint must have at least one test
- ✅ Every bug fix must have a test that fails before fix, passes after

**Rule 2: Test Structure**
```python
import unittest

class TestNewFeature(unittest.TestCase):
    """Test description"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Initialize test data
    
    def tearDown(self):
        """Clean up after tests"""
        # Clean up resources
    
    def test_success_case(self):
        """Test: Happy path"""
        # Arrange, Act, Assert
    
    def test_error_case(self):
        """Test: Error handling"""
        # Test error conditions
```

**Rule 3: Test Coverage**
- ✅ Success path (happy case)
- ✅ Error cases (negative scenarios)
- ✅ Edge cases (boundaries, null values)
- ✅ Data validation
- ✅ Authorization/authentication

**Rule 4: Test Execution**
```bash
# BEFORE COMMIT: Run all tests
python3 -m unittest discover

# BEFORE PUSH: Verify all tests pass
python3 -m unittest discover 2>&1 | grep "OK"
```

**Rule 5: Test Maintenance**
- ✅ Keep tests updated with code changes
- ✅ Update test names if requirements change
- ✅ Remove obsolete tests
- ✅ Add tests if edge cases found

---

## Logging Requirements

### Mandatory for All Code

**Rule 1: Log Levels**
- 🔴 **ERROR**: Failures, exceptions, critical issues
- 🟡 **WARNING**: Deprecated code, skipped operations, recoverable issues
- 🟢 **INFO**: Important events, user actions, milestones
- 🔵 **DEBUG**: Detailed flow, variable values, intermediate steps

**Rule 2: Logging Pattern**

```python
import logging
logger = logging.getLogger(__name__)

# At module level
logger.info(f"Starting operation: {operation_name}")
logger.debug(f"Input parameters: {params}")

try:
    result = perform_operation(data)
    logger.info(f"✅ Operation succeeded: {operation_name}")
    logger.debug(f"Result: {result}")
except Exception as e:
    logger.error(f"❌ Operation failed: {str(e)}")
    logger.debug(f"Exception trace: {traceback.format_exc()}")
    raise
finally:
    logger.debug("Cleaning up resources")
```

**Rule 3: Log What to Include**
- ✅ Function entry: `logger.info(f"Starting {function_name}(...)")`
- ✅ Decision points: `logger.debug(f"Branch: {condition} → {result}")`
- ✅ Database operations: `logger.debug(f"Query: {sql_statement}")`
- ✅ External calls: `logger.info(f"Calling {service}: {endpoint}")`
- ✅ Errors: `logger.error(f"❌ {description}: {error_details}")`
- ✅ Success: `logger.info(f"✅ {operation} completed successfully")`

**Rule 4: Sensitive Data**
- ❌ NEVER log passwords, tokens, API keys
- ❌ NEVER log full credit card numbers
- ❌ NEVER log personal identification numbers
- ✅ Log operation type: `"User login attempt for admin panel"`
- ✅ Log sanitized data: `"Processing user ID: {user_id}"`

**Rule 5: Log Format**
Use structured logging where possible:
```python
# Bad
logger.info("User logged in")

# Good
logger.info(f"✅ User login successful: license_id={license_id}, timestamp={timestamp}")
logger.debug(f"Login details: {{'ip': '{ip}', 'duration': {duration_ms}ms}}")
```

**Rule 6: Log Verbosity in Loops**
- ✅ Log before loop: `logger.info(f"Processing {count} items")`
- ✅ Log errors in loop: `logger.error(f"Error processing item {i}/{count}: {error}")`
- ✅ Log completion: `logger.info(f"✅ Completed processing {success_count}/{count} items")`
- ❌ Don't log every iteration (use debug for that)

```python
# Good pattern
logger.info(f"Starting to scrape {len(players)} players")
for i, player in enumerate(players, 1):
    try:
        result = scrape_player(player)
        logger.debug(f"Scraped player {i}: {player['name']}")
    except Exception as e:
        logger.error(f"Failed to scrape player {i}/{len(players)}: {str(e)}")
logger.info(f"✅ Finished scraping {len(players)} players")
```

---

## Change Documentation

### File: CHANGES.md (Required)

**Rule 1: Create/Update CHANGES.md**
- ✅ MUST be updated with EVERY commit
- ✅ Track what actually changed
- ✅ Include before/after comparisons
- ✅ Document breaking changes
- ✅ Note test coverage

**Rule 2: CHANGES.md Format**

```markdown
# Changes Log

## [Unreleased]

### Added
- New feature X (test coverage: 90%)
- New function Y in module Z (added 2 unit tests)

### Changed
- Modified endpoint /api/endpoint from pattern A to pattern B
  Before: Returns {old_format}
  After: Returns {new_format}
  Tests: Updated 3 tests, added 1 new test

### Fixed
- Bug: Player registration failed for certain levels
  Root cause: Query used old schema
  Solution: Updated to use license_id instead of player_id
  Tests: Added test_player_registration_fix()

### Removed
- Removed deprecated function get_tournament_db()
  Migration path: Use get_tournament_by_id() instead

### Security
- Fixed SQL injection vulnerability in search endpoint
  Impact: Medium - affected user search only
  Tests: Added 2 security tests

### Database
- Schema change: Added 'ranking' JSON column to players table
  Migration: migrate_players_db.py executed successfully
  Backup: players.db.backup.20260813_latest

### Breaking Changes
- API response format for /api/tournaments changed
  Old: {db_file, name, levels}
  New: {id, tournament_name, location, date_start}
  Migration guide: See API_MIGRATION_GUIDE.md

---

## [2026-08-13] Phase 5 Complete

### Added
- ENDPOINT_REFACTORING.md (447 lines) - Reference implementations for 11 endpoints
- REFACTORED_ENDPOINTS.py (535 lines) - Copy-paste ready code
- test_integration.py - 7 integration tests
- API_MIGRATION_GUIDE.md - Developer migration guide

### Changed
- app.py - Added player scraper integration (2 locations)
- drive_sync.py - Removed tournament/ directory syncing
- Refactored GET /api/tournaments endpoint

### Tests Added
- TestDatabaseIntegration (3 tests)
- TestPlayerDataFlow (2 tests)
- TestDataPersistence (1 test)
- TestConstraints (1 test)
All tests passing ✅

---

## [2026-08-12] Phase 4

(Previous entries...)
```

**Rule 3: CHANGES.md Entry Timing**
- ✅ Update CHANGES.md as you make changes (not at the end)
- ✅ Add entries before each commit
- ✅ Reference ticket/issue numbers if available
- ✅ Include test count and status

**Rule 4: What to Document**
```markdown
### Changed
- [FILE] - [WHAT CHANGED]
  Before: [OLD BEHAVIOR]
  After: [NEW BEHAVIOR]
  Tests: [TEST CHANGES]
  Impact: [WHO IS AFFECTED]
```

**Rule 5: Review CHANGES.md Before Commit**
```bash
# Before committing, verify CHANGES.md is complete
cat CHANGES.md | head -30

# Verify format is correct
grep -E "^### (Added|Changed|Fixed|Removed|Security|Database|Breaking)" CHANGES.md
```

---

## Project Focus

### Rule 1: Single Project at a Time
- ✅ Work ONLY on `/local/badmintonScrapPython`
- ✅ Keep context in this project
- ✅ Don't switch to other projects mid-task
- ✅ Complete tasks before switching

**Verification**:
```bash
# Always verify correct directory
pwd  # Should show: /home/eumasra/Downloads or /local/badmintonScrapPython
cd /local/badmintonScrapPython
git status  # Should show badmintonScrapPython repo
```

### Rule 2: Task Boundaries
- ✅ Complete one task fully before starting another
- ✅ Update CHANGES.md for each task
- ✅ Get user approval before moving to next task
- ✅ Document dependencies between tasks

### Rule 3: Context Awareness
- ✅ Reference previous work: "From Phase 4, we have..."
- ✅ Build on existing code: "Using the players_scraper module..."
- ✅ Maintain consistency with established patterns
- ✅ Follow existing code style

---

## Git Workflow

### Rule 1: Commit Requirements (BEFORE PUSH)

✅ **MUST DO**:
1. Write unit test for new code
2. Run all tests: `python3 -m unittest discover`
3. Verify tests pass: `Ran X tests - OK`
4. Update CHANGES.md
5. Review changes: `git diff --staged`
6. Verify no secrets: `git diff | grep -i password`
7. **ASK USER**: "Ready to push X commits?"

❌ **MUST NOT DO**:
- Push without testing
- Push without unit tests
- Push without user approval
- Push with uncommitted changes to CHANGES.md
- Push with secrets/credentials visible

### Rule 2: Commit Message Format

```
[Type]: Brief description (max 70 chars)

DETAILED DESCRIPTION

Changes:
✅ What was added
✅ What was changed
✅ What was fixed

Testing:
- Test A verifies X
- Test B verifies Y
Tests: Ran 25 tests - OK

Impact:
- Users: Feature now available
- Admins: No action required
- Database: No schema changes
```

**Type Options**: Feature, Fix, Docs, Refactor, Test, Security, Migration

### Rule 3: Pre-Push Checklist

```bash
# Before pushing EVERY TIME:

# 1. Verify directory
pwd
cd /local/badmintonScrapPython

# 2. Check status
git status  # Should show no uncommitted changes

# 3. Run all tests
python3 -m unittest discover
# Should show: Ran X tests in X.XXXs - OK

# 4. Verify CHANGES.md is updated
head -20 CHANGES.md

# 5. Review commits to push
git log --oneline -5

# 6. Check for secrets
git diff HEAD~1 | grep -iE "password|token|secret|api.?key"
# Should return nothing

# 7. Ask user
echo "Ready to push 2 commits?"

# 8. Only push after user says yes
git push origin main
```

### Rule 4: Atomic Commits
- ✅ One feature = one logical commit
- ✅ Keep commits focused and reviewable
- ✅ Don't mix unrelated changes
- ✅ Each commit should work independently

```bash
# Good
commit 1: "Feature: Add player scraper to startup"
commit 2: "Test: Add 3 tests for player scraper"
commit 3: "Docs: Update CHANGES.md"

# Bad
commit 1: "Feature: Add scraper, update docs, fix bug, refactor code"
```

---

## Code Review Process

### Rule 1: Before Starting Work

```
1. Read the requirements carefully
2. Check existing code patterns
3. Review CHANGES.md for context
4. Understand current test coverage
5. Ask questions if unclear
```

### Rule 2: During Development

```
1. Write test first (TDD approach)
2. Implement feature
3. Verify tests pass
4. Add logging throughout
5. Update CHANGES.md incrementally
6. Review code for style consistency
```

### Rule 3: Before Requesting User Approval

**Verification Checklist**:
- [ ] All new code has unit tests
- [ ] All tests passing: `Ran X tests - OK`
- [ ] Code compiles: `python3 -m py_compile module.py`
- [ ] Logging added at key points
- [ ] CHANGES.md updated
- [ ] No secrets in code
- [ ] No uncommitted changes
- [ ] Git history is clean
- [ ] Commit messages are clear

**Show User**:
```
✅ Task completed: [Task Name]

Deliverables:
- [File] with [X] lines of code
- [Test File] with [Y] unit tests

Changes:
✅ Added [feature]
✅ Fixed [issue]
✅ Updated [docs]

Test Results:
- Ran 25 tests in 0.123s - OK

Files Modified:
- app.py
- test_badminton.py
- CHANGES.md

Ready to push? [Yes/No]
```

### Rule 4: After User Approval

```bash
# 1. Final verification
python3 -m unittest discover

# 2. Review one more time
git diff

# 3. Push
git push origin main

# 4. Confirm success
git log --oneline -1
```

---

## Template for New Tasks

Use this template when starting any new task:

```markdown
# Task: [Task Name]

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3

## Implementation Plan
1. Write tests for requirement 1
2. Implement requirement 1
3. Verify tests pass
4. Update CHANGES.md
5. Request user approval

## Tests to Write
- test_requirement_1_success()
- test_requirement_1_error()
- test_requirement_2_success()

## Logging Strategy
- Log at entry: function_name() called
- Log at decision: if condition X → Y
- Log at exit: function_name() completed
- Log errors: Exception in function_name(): {error}

## Files to Modify
- [ ] app.py
- [ ] test_badminton.py
- [ ] CHANGES.md

## Verification Steps
1. [ ] All tests pass
2. [ ] Code compiles
3. [ ] Logging is comprehensive
4. [ ] CHANGES.md is updated
5. [ ] No secrets in code
6. [ ] User approval obtained
7. [ ] Ready to push
```

---

## Summary Checklist

### For Every Commit:
- [ ] Unit tests written FIRST
- [ ] All tests passing (19+ tests)
- [ ] Logging added (INFO, DEBUG, ERROR)
- [ ] CHANGES.md updated
- [ ] No uncommitted changes
- [ ] Commit message clear
- [ ] User approval obtained
- [ ] No secrets in code

### For Every Push:
- [ ] Run `python3 -m unittest discover` ✅ OK
- [ ] Review `CHANGES.md` for completeness
- [ ] Verify commit history is clean
- [ ] Check `git status` is clean
- [ ] Confirm with user
- [ ] No concurrent tasks
- [ ] Context is on badmintonScrapPython only

### For Every Feature:
- [ ] Test written first (TDD)
- [ ] Code implements feature
- [ ] Logging at 5+ key points
- [ ] Documentation updated
- [ ] CHANGES.md entry created
- [ ] No breaking changes OR documented migration
- [ ] Backward compatible OR deprecated gracefully

---

## Quick Reference

```bash
# Test before commit
python3 -m unittest discover

# Check what will be committed
git diff --staged

# Update CHANGES.md
nano CHANGES.md

# Stage changes
git add app.py test_badminton.py CHANGES.md

# Commit with message
git commit -m "Feature: Description

Changes:
✅ Added X
✅ Fixed Y

Tests: Ran 25 tests - OK"

# Before push - ask user
echo "Ready to push?"

# After user approval
git push origin main
```

---

## Effective Date

**This document is effective immediately (2026-08-13).**

All work on badmintonScrapPython must follow these guidelines.

**Changes to these guidelines require explicit user approval.**

---

**Version History**:
- v1.0 (2026-08-13): Initial version, comprehensive guidelines for testing, logging, changes documentation, project focus, and git workflow.
