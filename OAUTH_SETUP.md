# OAuth Setup for Google Drive Sync

This guide explains how to set up OAuth 2.0 credentials for badmintonScrapPython to sync with your personal Google Drive.

## Why OAuth Instead of Service Account?

Service accounts have **no storage quota** - they can't upload to personal Google Drive. OAuth uses **your Google account's storage**, which is unlimited for personal use.

## Setup Steps

### Step 1: Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Make sure you're in the **BadmintonScrapPython** project
3. Go to **APIs & Services** > **Credentials**
4. Click **+ CREATE CREDENTIALS** > **OAuth client ID**
5. If asked, configure the OAuth consent screen first:
   - User Type: **External**
   - App name: `BadmintonScrapPython`
   - User support email: Your email
   - Developer contact: Your email
   - Save and continue (don't need to add scopes)
6. Back to credentials:
   - Application type: **Desktop application**
   - Name: `BadmintonScrapPython`
   - Click **CREATE**
7. Download the JSON file (click download icon)
   - Save as `oauth_credentials.json`

### Step 2: Get Your Refresh Token

You need to authorize the app once to get a refresh token. Here's how:

**On Your Local Machine:**

1. Create a script `get_refresh_token.py`:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

# Path to your downloaded OAuth credentials JSON
CLIENT_SECRET_FILE = 'oauth_credentials.json'

# Scopes
SCOPES = ['https://www.googleapis.com/auth/drive']

# Create flow
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)

# This opens browser for authorization
credentials = flow.run_local_server(port=8080)

# Print refresh token
print(f"\n✅ Refresh Token: {credentials.refresh_token}")
print(f"Client ID: {credentials.client_id}")
print(f"Client Secret: {credentials.client_secret}")
```

2. Run the script:
```bash
python3 get_refresh_token.py
```

3. A browser window opens - sign in with your Google account
4. Grant permission to access Google Drive
5. Script prints your **refresh token** - **SAVE THIS!**

### Step 3: Add Credentials to Render

In Render Dashboard, add these environment variables:

1. **GOOGLE_DRIVE_REFRESH_TOKEN**
   - Value: The refresh token from Step 2
   
2. **GOOGLE_DRIVE_CLIENT_ID**
   - Value: From `oauth_credentials.json` (look for `"client_id"`)
   
3. **GOOGLE_DRIVE_CLIENT_SECRET**
   - Value: From `oauth_credentials.json` (look for `"client_secret"`)
   
4. **GOOGLE_DRIVE_SYNC_FOLDER_ID**
   - Value: Your folder ID (same as before, e.g., `1HTj4fX91U5_dQOi1mICXS86kHgtnKutX`)

### Step 4: Deploy and Test

1. Push code to GitHub (already done)
2. Render auto-deploys
3. Check logs for:
   ```
   ✅ Google Drive client initialized (OAuth)
   ✅ Uploading initialized databases to Google Drive...
   ```
4. Check your Google Drive folder - files should appear!

---

## Verification

After deployment:

1. Go to Google Drive: https://drive.google.com/
2. Open folder `BadmintonScrapPython-Databases`
3. You should see:
   - `admin.db`
   - `point_rules.db`
   - Any tournament `.db` files
4. Files should have today's timestamp

---

## How OAuth Works

```
Render App
  ↓
Uses refresh token to get access token
  ↓
Access token grants permission to YOUR Google Drive
  ↓
Upload to YOUR Google Drive folder (using YOUR storage quota)
```

---

## Security Notes

⚠️ **Important:**
- Never share your `refresh_token` or `oauth_credentials.json`
- Keep them secret in Render environment variables
- Refresh tokens don't expire (unless revoked)
- You can revoke access anytime from Google Account settings

---

## Troubleshooting

### "Credentials not set"
- Check all 4 environment variables are in Render
- Verify exact spelling (including underscores)

### "Invalid refresh token"
- Refresh token might have expired
- Re-run `get_refresh_token.py` to get a new one
- Update in Render

### "Permission denied"
- Check that you signed in with the correct Google account
- Refresh token is tied to that account

### "File not found"
- Check folder ID is correct (your Google Drive folder ID)
- Should be a long string of letters/numbers

---

## Next Steps

After OAuth is set up:
1. App syncs databases every 10 seconds (debounce)
2. Fallback sync every 5 minutes
3. All data backed up to YOUR Google Drive
4. Works even if Render service idles

Enjoy automatic backups! 🎉
