# Local dev launcher. Production (Docker) ignores this and keeps the 3000 default.
$env:PORT = "3002"
# Off because the app is reachable over Tailscale; the Werkzeug debugger would be too.
# Set to 1 if you need interactive tracebacks and are not sharing the tailnet URL.
$env:DEBUG = "0"
# Keep local databases and backups out of the repo root.
$env:DATA_DIR = "$PSScriptRoot\data-local"
# Never mail real players from a dev box. Set to 1 only to test against a throwaway Brevo account.
$env:EMAIL_ENABLED = "0"
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\app.py"
