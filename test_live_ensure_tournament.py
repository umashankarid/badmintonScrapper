"""
Live test: Call ensure_tournament() and check what gets saved

This script will:
1. Delete the old tournament record from tournaments.db
2. Call ensure_tournament() with the Vikingaslaget URL
3. Check what was actually saved
4. Show all the logs and data
"""

import sqlite3
import requests
import json
import os
from datetime import datetime

TOURNAMENTS_DB = "tournaments.db"
URL = "https://badmintonsweden.tournamentsoftware.com/tournament/77FEC02B-4489-4D4C-A71F-C6844BAEB2BA"

print("=" * 80)
print("LIVE TEST: ensure_tournament() ENDPOINT")
print("=" * 80)

# Step 1: Delete old record
print("\nStep 1: Cleaning old tournament record...")
try:
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM tournaments WHERE tournament_url = ?", (URL,))
    conn.commit()
    print(f"  ✅ Deleted old record")
    
    # Verify it's deleted
    cur.execute("SELECT COUNT(*) FROM tournaments WHERE tournament_url = ?", (URL,))
    count = cur.fetchone()[0]
    print(f"  ✅ Verified: {count} records remain")
    conn.close()
except Exception as e:
    print(f"  ❌ Error: {e}")
    exit(1)

# Step 2: Call the endpoint
print(f"\nStep 2: Calling ensure_tournament() endpoint...")
print(f"  URL: {URL}")

try:
    response = requests.post(
        "http://localhost:3000/api/ensure-tournament",
        json={"url": URL},
        timeout=30
    )
    print(f"  Status: {response.status_code}")
    result = response.json()
    print(f"  Response: {json.dumps(result, indent=2)}")
    
    if not result.get('success'):
        print(f"  ❌ Endpoint failed: {result.get('error')}")
        exit(1)
    
    print(f"  ✅ Endpoint successful")
except Exception as e:
    print(f"  ❌ Error calling endpoint: {e}")
    print(f"\n  Note: Make sure the Flask app is running on localhost:3000")
    print(f"  Run: python3 app.py")
    exit(1)

# Step 3: Check what was saved
print(f"\nStep 3: Checking what was saved to tournaments.db...")

conn = sqlite3.connect(TOURNAMENTS_DB)
cur = conn.cursor()

cur.execute("""
    SELECT tournament_url, tournament_name, location, date_start, date_end,
           registration_opens, registration_closes, cancellation_deadline,
           competition_start, competition_end, selected_for_view
    FROM tournaments WHERE tournament_url = ?
""", (URL,))

row = cur.fetchone()
conn.close()

if not row:
    print(f"  ❌ No record found in database!")
    exit(1)

col_names = ['tournament_url', 'tournament_name', 'location', 'date_start', 'date_end',
             'registration_opens', 'registration_closes', 'cancellation_deadline',
             'competition_start', 'competition_end', 'selected_for_view']

data = dict(zip(col_names, row))

print(f"\n  Retrieved data from tournaments.db:")
print(f"  " + "-" * 76)
for key, val in data.items():
    status = "✅" if val else "❌"
    print(f"  {status} {key:30} = {val}")
print(f"  " + "-" * 76)

# Step 4: Verify all dates are populated
print(f"\nStep 4: Verification...")

errors = []
expected_dates = {
    'registration_opens': '2026-06-09',
    'registration_closes': '2026-08-15',
    'cancellation_deadline': '2026-08-15',
    'competition_start': '2026-08-29',
    'competition_end': '2026-08-30'
}

for field, expected_value in expected_dates.items():
    actual_value = data.get(field)
    if actual_value is None or actual_value == '':
        errors.append(f"  ❌ {field} is NULL or empty (expected: {expected_value})")
    elif actual_value == expected_value:
        print(f"  ✅ {field}: {actual_value} (correct)")
    else:
        errors.append(f"  ⚠️  {field}: {actual_value} (expected: {expected_value})")

if errors:
    print(f"\n❌ ERRORS FOUND:")
    for error in errors:
        print(error)
    exit(1)
else:
    print(f"\n✅ ALL DATES ARE CORRECTLY POPULATED!")
    print(f"\nThe fix is working correctly!")

print("\n" + "=" * 80)
