# Google Drive Sync Setup Guide

This document explains how to set up Google Drive persistence for badmintonScrapPython SQLite databases.

## Why This Matters

Render's free tier uses ephemeral storage - databases are lost when the container restarts. This setup ensures:
- ✅ Databases persist across container restarts
- ✅ Automatic backups to Google Drive
- ✅ No data loss on Render
- ✅ Works with Loopia too (same Google Drive)

## Setup Steps

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project"
3. Name it: `BadmintonScrapPython`
4. Click "Create"

### Step 2: Enable Google Drive API

1. In the Google Cloud Console, search for "Google Drive API"
2. Click "Enable"
3. You'll see "APIs & Services > Enabled APIs & services"

### Step 3: Create a Service Account

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in:
   - Service account name: `badminton-scraper`
   - Description: `Database sync for badminton scraper`
4. Click "Create and Continue"
5. Grant roles: Skip this step (click "Continue")
6. Click "Done"

### Step 4: Create and Download Service Account Key

1. In Credentials, find your service account: `badminton-scraper`
2. Click on it to open details
3. Go to "Keys" tab
4. Click "Add Key" > "Create new key"
5. Choose "JSON" format
6. Click "Create"
7. A JSON file will download - **keep this safe!**

### Step 5: Create a Google Drive Folder (Manual)

1. Go to [Google Drive](https://drive.google.com)
2. Create a new folder: `BadmintonScrapPython-Databases`
3. Right-click the folder > "Share"
4. Add your service account email (from the JSON file)
5. Give "Editor" permission
6. Click "Share"

### Step 6: Get Your Folder ID

1. Open the folder in Google Drive
2. Look at the URL: `https://drive.google.com/drive/folders/{FOLDER_ID}`
3. Copy the `FOLDER_ID` part

### Step 7: Prepare Credentials for Render

**Option A: Environment Variable (Recommended)**

1. Open the JSON file you downloaded
2. Copy the entire JSON content
3. In Render dashboard, go to your service's Environment
4. Add new environment variable:
   - Key: `GOOGLE_DRIVE_CREDENTIALS`
   - Value: Paste the entire JSON content

**Option B: Base64 Encoded (If Option A doesn't work)**

1. Convert JSON to base64:
   ```bash
   cat service-account.json | base64
   ```
2. Add to Render:
   - Key: `GOOGLE_DRIVE_CREDENTIALS_B64`
   - Value: Paste base64 string
3. Update `drive_sync.py` Line 30 to decode it first

### Step 8: Set Folder ID in Render

Add another environment variable in Render:
- Key: `GOOGLE_DRIVE_SYNC_FOLDER_ID`
- Value: Your folder ID from Step 6

### Step 9: Deploy and Test

1. Go to Render dashboard
2. Trigger a manual deploy
3. Check logs for:
   ```
   ✅ Google Drive client initialized
   ✅ Downloaded X database files from Google Drive
   ✅ Using existing Google Drive folder: [FOLDER_ID]
   ```

## Verification

### Check if Sync is Working

1. **On first startup:**
   - Render logs should show download messages
   - Check Google Drive folder - should be empty initially

2. **After using the app:**
   - Make some changes in the app
   - Check Google Drive folder
   - You should see: `players.db`, `admin.db`, `point_rules.db`
   - Plus any tournament `.db` files

3. **Test persistence:**
   - Make changes in the app
   - Restart the Render service
   - Changes should still be there (data came from Google Drive)

## Troubleshooting

### "Google Drive not authenticated"
- Check `GOOGLE_DRIVE_CREDENTIALS` is set correctly
- Verify JSON is valid (no corruption)
- Ensure service account has access to folder

### Files not uploading
- Check service account has "Editor" permission on folder
- Verify `GOOGLE_DRIVE_SYNC_FOLDER_ID` is set
- Check Render logs for upload errors

### Files not downloading
- Check if files exist in Google Drive folder
- Verify folder ID is correct
- Check service account permissions

### Too many API calls
- Google Drive API has rate limits
- Current implementation uploads only on shutdown
- Consider adding periodic sync if needed

## Local Testing

To test locally before deploying:

```bash
# Create a test credentials file
export GOOGLE_DRIVE_CREDENTIALS='{"type": "service_account", ...}'
export GOOGLE_DRIVE_SYNC_FOLDER_ID='your_folder_id'

# Run app
python app.py
```

## Advanced: Periodic Sync

Currently, databases are synced:
- **Download**: On app startup
- **Upload**: On app shutdown

To add periodic sync (every N minutes):

```python
# In app.py, add after imports:
from threading import Thread
import time

def periodic_sync():
    """Periodically upload databases"""
    while True:
        time.sleep(300)  # Every 5 minutes
        upload_all()

# Start background thread
Thread(target=periodic_sync, daemon=True).start()
```

## Files Modified

- `app.py`: Added sync on startup/shutdown
- `drive_sync.py`: New module with GoogleDriveSync class
- `requirements.txt`: Added Google API dependencies

## Rollback

If you need to revert to the previous version:

```bash
git checkout backup-before-google-drive-sync
# Or
git checkout v-stable-before-drive-sync
```

## Security Notes

⚠️ **Important:**
- Never commit `service-account.json` to Git
- Keep `GOOGLE_DRIVE_CREDENTIALS` secret in Render
- Don't share your credentials file
- Use service accounts, not personal Google credentials

## Questions?

If something doesn't work:
1. Check Render logs for errors
2. Verify all environment variables are set
3. Confirm service account has folder access
4. Test with local python first
