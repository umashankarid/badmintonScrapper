#!/usr/bin/env python3
"""
Migration script: Refactor players.db to new schema

Current schema:
- id (INTEGER PRIMARY KEY)
- name (TEXT)
- profile_url (TEXT)
- club (TEXT)
- gender (TEXT)

New schema:
- license_id (TEXT PRIMARY KEY) -- Unique identifier
- name (TEXT NOT NULL)
- profile_url (TEXT)
- club (TEXT)
- gender (TEXT)
- email (TEXT)
- phone (TEXT)
- dob (TEXT)
- age (TEXT)
- ranking (TEXT) -- JSON format
- last_updated (TIMESTAMP)
- last_scraped (TIMESTAMP)
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = 'players.db'
BACKUP_PATH = f'players.db.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'

def backup_database():
    """Create backup before migration"""
    print(f"📋 Creating backup: {BACKUP_PATH}")
    shutil.copy(DB_PATH, BACKUP_PATH)
    print(f"✅ Backup created")

def migrate_players_db():
    """Migrate players.db to new schema"""
    print("\n" + "=" * 80)
    print("🔄 MIGRATING players.db to New Schema")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Step 1: Get existing player data
    print("\n1️⃣  Reading existing player data...")
    cur.execute("SELECT id, name, profile_url, club, gender FROM players")
    player_data = cur.fetchall()
    print(f"   Found {len(player_data)} players")
    
    # Step 2: Rename old players table
    print("\n2️⃣  Renaming old players table...")
    cur.execute("ALTER TABLE players RENAME TO players_old")
    print("   ✅ Renamed players → players_old")
    
    # Step 3: Create new players table with new schema
    print("\n3️⃣  Creating new players table with expanded schema...")
    cur.execute("""
        CREATE TABLE players (
            license_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            profile_url TEXT,
            club TEXT,
            gender TEXT,
            email TEXT,
            phone TEXT,
            dob TEXT,
            age TEXT,
            ranking TEXT,
            last_updated TIMESTAMP,
            last_scraped TIMESTAMP
        )
    """)
    print("   ✅ Created new players table")
    
    # Step 4: Migrate data from old table
    print("\n4️⃣  Migrating data from old table...")
    for id, name, profile_url, club, gender in player_data:
        # Use profile_url as temporary license_id (will be updated from Badminton Sweden)
        license_id = f"temp_{id}"
        
        cur.execute("""
            INSERT INTO players 
            (license_id, name, profile_url, club, gender, last_updated, last_scraped)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (license_id, name, profile_url, club, gender, datetime.now().isoformat(), None))
    
    conn.commit()
    print(f"   ✅ Migrated {len(player_data)} players")
    
    # Step 5: Drop old table
    print("\n5️⃣  Removing old table...")
    cur.execute("DROP TABLE players_old")
    print("   ✅ Dropped players_old")
    
    # Step 6: Verify new structure
    print("\n6️⃣  Verifying new structure...")
    cur.execute("PRAGMA table_info(players)")
    columns = cur.fetchall()
    print(f"   Columns in new players table:")
    for col_id, col_name, col_type, not_null, default, pk in columns:
        pk_marker = " (PRIMARY KEY)" if pk else ""
        not_null_marker = " NOT NULL" if not_null else ""
        print(f"   • {col_name:<15} {col_type:<10}{pk_marker}{not_null_marker}")
    
    # Step 7: Get row count
    cur.execute("SELECT COUNT(*) FROM players")
    count = cur.fetchone()[0]
    
    # Step 8: Show sample data
    print(f"\n7️⃣  Sample data (first 3 rows):")
    cur.execute("SELECT license_id, name, club FROM players LIMIT 3")
    for license_id, name, club in cur.fetchall():
        print(f"   • {license_id}: {name} ({club})")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ MIGRATION COMPLETE")
    print("=" * 80)
    print(f"\n📊 Migration Summary:")
    print(f"   ✅ Total players migrated: {count}")
    print(f"   ✅ New schema: license_id (PK), name, profile_url, club, gender")
    print(f"   ✅ New fields: email, phone, dob, age, ranking, last_updated, last_scraped")
    print(f"\n💾 Backup created at: {BACKUP_PATH}")
    print(f"   Keep this until you verify everything works!")

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: {DB_PATH} not found")
        exit(1)
    
    backup_database()
    migrate_players_db()
    
    print("\n" + "=" * 80)
    print("📝 NEXT STEPS:")
    print("=" * 80)
    print("1. Verify the migration looks good")
    print("2. Run unit tests to ensure nothing broke")
    print("3. Delete backup if migration successful: rm " + BACKUP_PATH)
    print("=" * 80)
