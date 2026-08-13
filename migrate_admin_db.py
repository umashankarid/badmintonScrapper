#!/usr/bin/env python3
"""
Migration script: Refactor admin.db to clean structure

Current structure:
- admins table
- bwf_tournament_visibility table (to be removed)
- tournament_visibility table (legacy, empty)
- smtp_settings table (empty, keep for future)
- reminders_sent table (empty, keep for future)

New structure:
- admin_users table (renamed from admins)
- smtp_settings table (keep)
- reminders_sent table (keep)
- (Remove bwf_tournament_visibility - move to tournaments.db)
- (Remove tournament_visibility - legacy)
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = 'admin.db'
BACKUP_PATH = f'admin.db.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'

def backup_database():
    """Create backup before migration"""
    print(f"📋 Creating backup: {BACKUP_PATH}")
    shutil.copy(DB_PATH, BACKUP_PATH)
    print(f"✅ Backup created")

def migrate_admin_db():
    """Migrate admin.db to new structure"""
    print("\n" + "=" * 80)
    print("🔄 MIGRATING admin.db to Clean Structure")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Step 1: Get existing admin data
    print("\n1️⃣  Reading existing admin data...")
    cur.execute("SELECT id, username, password FROM admins")
    admin_data = cur.fetchall()
    print(f"   Found {len(admin_data)} admin users:")
    for id, username, password in admin_data:
        print(f"   - {username}")
    
    # Step 2: Drop old tournament visibility tables
    print("\n2️⃣  Removing legacy tournament visibility tables...")
    cur.execute("DROP TABLE IF EXISTS bwf_tournament_visibility")
    print("   ✅ Dropped bwf_tournament_visibility")
    cur.execute("DROP TABLE IF EXISTS tournament_visibility")
    print("   ✅ Dropped tournament_visibility (legacy)")
    
    # Step 3: Rename admins table to admin_users
    print("\n3️⃣  Renaming admins table to admin_users...")
    cur.execute("ALTER TABLE admins RENAME TO admin_users")
    print("   ✅ Renamed admins → admin_users")
    
    # Step 4: Verify new structure
    print("\n4️⃣  Verifying new structure...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cur.fetchall()
    print(f"   Tables in admin.db:")
    for (table_name,) in tables:
        if not table_name.startswith('sqlite_'):
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"   ✅ {table_name} ({count} rows)")
    
    # Step 5: Display admin_users table structure
    print("\n5️⃣  Admin Users Table Structure:")
    cur.execute("PRAGMA table_info(admin_users)")
    columns = cur.fetchall()
    for col_id, col_name, col_type, not_null, default, pk in columns:
        pk_marker = " (PRIMARY KEY)" if pk else ""
        not_null_marker = " NOT NULL" if not_null else ""
        print(f"   • {col_name}: {col_type}{pk_marker}{not_null_marker}")
    
    # Step 6: Display SMTP Settings structure
    print("\n6️⃣  SMTP Settings Table Structure:")
    cur.execute("PRAGMA table_info(smtp_settings)")
    columns = cur.fetchall()
    for col_id, col_name, col_type, not_null, default, pk in columns:
        pk_marker = " (PRIMARY KEY)" if pk else ""
        not_null_marker = " NOT NULL" if not_null else ""
        print(f"   • {col_name}: {col_type}{pk_marker}{not_null_marker}")
    
    # Step 7: Display Reminders Sent structure
    print("\n7️⃣  Reminders Sent Table Structure:")
    cur.execute("PRAGMA table_info(reminders_sent)")
    columns = cur.fetchall()
    for col_id, col_name, col_type, not_null, default, pk in columns:
        pk_marker = " (PRIMARY KEY)" if pk else ""
        not_null_marker = " NOT NULL" if not_null else ""
        print(f"   • {col_name}: {col_type}{pk_marker}{not_null_marker}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ MIGRATION COMPLETE")
    print("=" * 80)
    print("\n📊 Final admin.db Structure:")
    print("   ✅ admin_users table (admin credentials)")
    print("   ✅ smtp_settings table (email configuration)")
    print("   ✅ reminders_sent table (tracking sent reminders)")
    print("\n   ✅ Removed: bwf_tournament_visibility table")
    print("   ✅ Removed: tournament_visibility table (legacy)")
    print("\n💾 Backup created at: " + BACKUP_PATH)

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: {DB_PATH} not found")
        exit(1)
    
    backup_database()
    migrate_admin_db()
    
    print("\n✅ All done! You can delete the backup if migration looks good:")
    print(f"   rm {BACKUP_PATH}")
