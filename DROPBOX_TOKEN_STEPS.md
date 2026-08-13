# Dropbox Token Steps

## Current Setup (Updated)

The app syncs SQLite databases to Dropbox using **refresh tokens** for reliable auto-renewal.

### How Authentication Works

1. **Preferred:** Uses `DROPBOX_REFRESH_TOKEN` — the Dropbox SDK handles token refresh automatically
2. **Fallback:** Uses `DROPBOX_ACCESS_TOKEN` — if refresh token not set, uses direct access token
3. **Auto-refresh:** If access token expires, automatically uses refresh token to get a new one

### Environment Variables (set in Render)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DROPBOX_REFRESH_TOKEN` | ✅ Yes | Long-lived refresh token (never expires) |
| `DROPBOX_APP_KEY` | Optional | App key (default: `2e0bvquyns4t5sb`) |
| `DROPBOX_APP_SECRET` | Optional | App secret (default in code) |
| `DROPBOX_ACCESS_TOKEN` | Optional | Fallback if refresh token not set |
| `DROPBOX_SYNC_FOLDER` | Optional | Folder path (default: `/BadmintonScrapPython-Databases`) |

### Files Synced

- `players.db`
- `admin.db`
- `point_rules.db`
- `tournaments.db`

### Sync Triggers

- **On startup:** Downloads all DBs from Dropbox
- **After any DB change:** Debounced upload (10 seconds after last change)
- **Every 5 minutes:** Periodic fallback sync
- **On shutdown:** Final upload

---

## How to Generate a Refresh Token (One-Time Setup)

### Step 1: Authorize the App

Open this URL in your browser:

```
https://www.dropbox.com/oauth2/authorize?client_id=2e0bvquyns4t5sb&response_type=code&token_access_type=offline
```

- Log in to your Dropbox account
- Click "Allow" to authorize the app
- Copy the **authorization code** shown on screen

### Step 2: Exchange Code for Refresh Token

Run this command (replace `YOUR_AUTH_CODE` with the code from Step 1):

```bash
curl -X POST https://api.dropboxapi.com/oauth2/token \
  -d code=YOUR_AUTH_CODE \
  -d grant_type=authorization_code \
  -d client_id=2e0bvquyns4t5sb \
  -d client_secret=9hljwc9w0c790w7
```

Response:
```json
{
  "access_token": "sl.xxxxx...",
  "token_type": "bearer",
  "expires_in": 14400,
  "refresh_token": "xxxxxxxxxxxxxxx",
  "scope": "...",
  "uid": "...",
  "account_id": "..."
}
```

### Step 3: Save the Refresh Token

Copy the `refresh_token` value and set it in Render:

```
DROPBOX_REFRESH_TOKEN=xxxxxxxxxxxxxxx
```

**Done!** The refresh token never expires. The app will automatically generate new access tokens as needed.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "DROPBOX_REFRESH_TOKEN not set" | Follow Steps 1-3 above |
| "Refresh token auth failed" | Token was revoked. Generate a new one (Steps 1-3) |
| "sync DISABLED" | No valid token available. Check env vars |
| Token works locally but not on Render | Make sure env var is set in Render dashboard |

---

## Quick Reference: Sync Flow

```
app.py startup
  → download_all()          # Get DBs from Dropbox
  → init databases          # Create tables if needed
  → upload_all()            # Backup initialized DBs

After any DB change
  → trigger_sync()          # Debounced (10s delay)
  → upload_all()            # Uploads all 4 DB files

On shutdown
  → sync_on_shutdown()      # Final upload
```
