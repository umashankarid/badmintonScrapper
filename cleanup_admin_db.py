"""
Migration: Remove legacy tournament_visibility table from admin.db

This table is no longer needed because:
1. We migrated to unified tournaments.db schema
2. Visibility is now tracked with 'selected_for_view' flag in tournaments table
3. No code references tournament_visibility anymore
4. It's dead code taking up space

This script safely removes the legacy table.
"""

import sqlite3
import os
import shutil
from datetime import datetime

ADMIN_DB = "admin.db"

def remove_tournament_visibility_table():
    """Remove legacy tournament_visibility table"""
    
    if not os.path.exists(ADMIN_DB):
        print(f"❌ {ADMIN_DB} not found")
        return False
    
    # Create backup
    backup_path = f"{ADMIN_DB}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(ADMIN_DB, backup_path)
    print(f"✅ Created backup: {backup_path}")
    
    try:
        conn = sqlite3.connect(ADMIN_DB)
        cur = conn.cursor()
        
        # Check if table exists
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='tournament_visibility'
        """)
        
        if not cur.fetchone():
            print("✅ tournament_visibility table doesn't exist (already removed)")
            conn.close()
            return True
        
        # Get row count before deletion
        cur.execute("SELECT COUNT(*) FROM tournament_visibility")
        count = cur.fetchone()[0]
        print(f"📊 Found {count} rows in tournament_visibility table")
        
        # Drop the table
        cur.execute("DROP TABLE tournament_visibility")
        conn.commit()
        
        print("✅ Dropped tournament_visibility table")
        
        # Verify it's gone
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='tournament_visibility'
        """)
        
        if cur.fetchone():
            print("❌ Table still exists!")
            conn.close()
            return False
        
        conn.close()
        
        # List remaining tables
        conn = sqlite3.connect(ADMIN_DB)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        remaining_tables = [row[0] for row in cur.fetchall()]
        conn.close()
        
        print(f"\n✅ Migration complete!")
        print(f"   Remaining tables in admin.db:")
        for table in remaining_tables:
            if table != 'sqlite_sequence':
                print(f"     - {table}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print(f"⚠️  Restoring from backup: {backup_path}")
        shutil.copy2(backup_path, ADMIN_DB)
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Removing legacy tournament_visibility table")
    print("=" * 60)
    print()
    
    success = remove_tournament_visibility_table()
    
    if success:
        print("\n✅ Migration successful - admin.db cleaned")
    else:
        print("\n❌ Migration failed - admin.db restored from backup")
