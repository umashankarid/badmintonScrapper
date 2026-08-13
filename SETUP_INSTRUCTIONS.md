# Setup Instructions - Auto-Token Management

## Quick Start

### Step 1: Encrypt Your Dropbox Credentials (One-Time)

On **your local computer**, run:

```bash
cd /local/badmintonScrapPython
python3 encrypt_credentials.py
```

**What it asks for:**
- Your Dropbox email
- Your Dropbox password

**What it outputs:**
- A long encrypted string (e.g., `gAAAAABlw...`)

**Copy this string carefully** - you'll need it in Step 2.

### Step 2: Get Initial Access Token

1. Go to: https://www.dropbox.com/developers/apps
2. Click your app (2e0bvquyns4t5sb)
3. Scroll to **"Generated access token"** section
4. Click **"Generate"**
5. Copy the token (long string starting with `sl.`)

### Step 3: Add to Render Environment

1. Go to Render Dashboard
2. Click your app: **badmintonscrapper**
3. Go to **Environment** tab
4. Add two new variables:

**Variable 1:**
```
Name: DROPBOX_ENCRYPTED_CREDS
Value: [paste the encrypted string from Step 1]
```

**Variable 2:**
```
Name: DROPBOX_ACCESS_TOKEN
Value: [paste the token from Step 2]
```

5. Click **Save** (auto-deploys)

### Step 4: Verify Deployment

Wait for deployment to complete. Check logs:

```
✅ ALL 12 TESTS PASSED - Startup approved
✅ Dropbox client initialized with valid token
✅ Downloaded 4 database files from Dropbox
```

If you see these messages, you're good! ✅

## How It Works Now

### On Startup
```
1. Run unit tests (12 tests)
   ├─ If any fail → Build blocked, deployment aborted
   └─ If all pass → Continue to Dropbox sync
   
2. Download databases from Dropbox
   ├─ Download tournaments.db with all data
   ├─ Download player registrations
   └─ Get latest tournament selections

3. Start Flask app
   └─ Ready for traffic
```

### When You Save Data
```
1. Register a player
2. Trigger sync (after 10 seconds of no changes)
3. Auto-encrypt data
4. Upload to Dropbox
5. Data persists forever ✅
```

### When Token Expires (~4 hours)
```
1. App detects expired token
2. Auto-generates new token using encrypted credentials
3. Retries Dropbox operation
4. **No manual action needed** ✅
```

## Testing

### Run Tests Locally
```bash
python3 -m unittest test_badminton -v
```

**Should see:**
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

### Verify in Render
After deployment, check **Logs** tab:
```
🧪 Running Pre-Startup Unit Tests
test_foreign_key_constraint ... ok
test_unique_constraint ... ok
... (all 12)
✅ ALL 12 TESTS PASSED - Startup approved
✅ Dropbox client initialized with valid token
```

## Troubleshooting

### Build Failed - Tests Failed
**Error in logs**: `❌ TEST FAILURES DETECTED`

**Fix**:
1. Read the failure details in logs
2. Report to developer
3. Wait for fix
4. Redeploy will auto-retry tests

### Startup Failed - Invalid Credentials
**Error in logs**: `❌ Failed to decrypt Dropbox credentials`

**Fix**:
1. Verify `DROPBOX_ENCRYPTED_CREDS` is correct
2. Re-run `python3 encrypt_credentials.py` locally
3. Update `DROPBOX_ENCRYPTED_CREDS` with new string
4. Redeploy

### Startup Failed - Token Expired
**Error in logs**: `⚠️ Access token expired - attempting to generate new one...`

**Fix**:
1. Auto-generation should handle it automatically
2. If it fails, generate new token from Dropbox app page
3. Update `DROPBOX_ACCESS_TOKEN` in Render
4. Redeploy

## What Each Variable Does

### DROPBOX_ENCRYPTED_CREDS
- Your Dropbox email + password, encrypted
- Used to auto-generate access tokens
- Safe to store (encrypted)
- Created by `encrypt_credentials.py`

### DROPBOX_ACCESS_TOKEN
- Current access token for Dropbox API
- Expires after ~4 hours of use
- Auto-refreshed using `DROPBOX_ENCRYPTED_CREDS`
- Can be any value initially

### DROPBOX_SYNC_FOLDER
- Where databases are stored in Dropbox
- Default: `/BadmintonScrapPython-Databases`
- (Already set, no need to change)

## Data Now Persists

✅ Tournament selections (which tournaments to show)  
✅ Player registrations (who's playing in what tournament)  
✅ Tournament metadata (dates, locations)  
✅ Admin settings  
✅ Scoring rules  

All this data:
- **Backs up to Dropbox** automatically
- **Survives redeploys** indefinitely
- **Auto-syncs** every 5 minutes (fallback)
- **Syncs immediately** after saves (debounce)

## Daily Usage

**Nothing changes for users!**

Admins can:
1. Select tournaments to display ✅ (persists)
2. Users can register for tournaments ✅ (persists)
3. Data backs up automatically ✅ (no manual steps)

## Monthly Maintenance

No monthly maintenance needed!

The system:
- Auto-generates new tokens ✅
- Auto-encrypts credentials ✅
- Auto-syncs data ✅
- Auto-runs tests on deploy ✅

## Emergency: Lost Data?

If data is somehow lost locally:
1. New container will download from Dropbox ✅
2. Redeploy will restore everything
3. No manual restore needed

If Dropbox is also corrupted:
1. Data loss is real (but rare)
2. Backups would need to be restored
3. Ask developer for help

## Questions?

**"When does my token refresh?"**  
Automatically when it expires (~4 hours). You don't do anything.

**"What if I forget my password?"**  
You'll need to generate new credentials. Run encrypt_credentials.py again with new credentials.

**"Can I change my password?"**  
Yes! Just re-run encrypt_credentials.py with new password, update DROPBOX_ENCRYPTED_CREDS in Render, and redeploy.

**"What if the encrypted string gets leaked?"**  
It's worthless without the app secret. Still, treat it like a password - keep it safe.

**"Do I need to do anything after each deploy?"**  
No! Tests run automatically, tokens refresh automatically, syncing happens automatically.

---

**Setup is complete! Your data is now safe and persistent.** ✅
