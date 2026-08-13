"""
Migration: Normalize tournament_*_registrations tables

Remove duplicated player data (name, club, gender, email, phone, dob, age, ranking)
and use foreign key references to players table instead.

Schema Changes:
OLD: tournament_*_registrations had redundant player columns
NEW: tournament_*_registrations only stores tournament-specific data + license_id FK

Benefits:
✅ No data duplication
✅ Single source of truth for player data
✅ Automatic consistency when player updates
✅ Reduced database size
✅ Proper referential integrity
"""

import sqlite3
import os
import shutil
from datetime import datetime

TOURNAMENTS_DB = "tournaments.db"
PLAYERS_DB = "players.db"

def migrate_registrations_to_normalized():
    """Migrate from denormalized to normalized registration tables"""
    
    if not os.path.exists(TOURNAMENTS_DB):
        print(f"❌ {TOURNAMENTS_DB} not found")
        return False
    
    # Create backup
    backup_path = f"{TOURNAMENTS_DB}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(TOURNAMENTS_DB, backup_path)
    print(f"✅ Created backup: {backup_path}")
    
    try:
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Find all registration tables
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE 'tournament_%_registrations'
            ORDER BY name
        """)
        
        tables = [row[0] for row in cur.fetchall()]
        
        if not tables:
            print("✅ No registration tables found - already normalized")
            conn.close()
            return True
        
        print(f"\n📊 Found {len(tables)} registration table(s)")
        
        for table_name in tables:
            print(f"\n  Processing: {table_name}")
            
            # Get current schema
            cur.execute(f"PRAGMA table_info({table_name})")
            current_columns = {row[1]: row[2] for row in cur.fetchall()}
            
            # Check if already normalized (no player data columns)
            player_data_cols = {'name', 'club', 'gender', 'email', 'phone', 'dob', 'age', 'ranking'}
            has_denormalized = any(col in current_columns for col in player_data_cols)
            
            if not has_denormalized:
                print(f"    ✅ Already normalized (no denormalized columns)")
                continue
            
            print(f"    📋 Current columns: {', '.join(current_columns.keys())}")
            
            # Get row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cur.fetchone()[0]
            print(f"    📊 Rows: {row_count}")
            
            # Get data before schema change
            cur.execute(f"SELECT * FROM {table_name}")
            old_data = cur.fetchall()
            old_column_names = [col[0] for col in cur.description]
            
            # Extract only necessary tournament-specific columns
            # Preserve: id, license_id, singles_level, doubles_level, mixed_level, 
            #           doubles_partner, mixed_partner, registration_date
            
            necessary_cols = {
                'id', 'license_id', 'singles_level', 'doubles_level', 'mixed_level',
                'doubles_partner', 'mixed_partner', 'registration_date'
            }
            
            # Rename table
            temp_table = f"{table_name}_old"
            cur.execute(f"ALTER TABLE {table_name} RENAME TO {temp_table}")
            print(f"    ✅ Renamed to: {temp_table}")
            
            # Create new normalized table
            cur.execute(f"""
                CREATE TABLE {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_id TEXT NOT NULL,
                    singles_level TEXT,
                    doubles_level TEXT,
                    mixed_level TEXT,
                    doubles_partner TEXT,
                    mixed_partner TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (license_id) REFERENCES players(license_id)
                )
            """)
            print(f"    ✅ Created normalized table")
            
            # Migrate data
            col_indices = {name: idx for idx, name in enumerate(old_column_names)}
            
            migrated = 0
            for row in old_data:
                try:
                    # Extract only necessary fields
                    license_id = row[col_indices.get('license_id')]
                    singles_level = row[col_indices.get('singles_level')] if 'singles_level' in col_indices else None
                    doubles_level = row[col_indices.get('doubles_level')] if 'doubles_level' in col_indices else None
                    mixed_level = row[col_indices.get('mixed_level')] if 'mixed_level' in col_indices else None
                    doubles_partner = row[col_indices.get('doubles_partner')] if 'doubles_partner' in col_indices else None
                    mixed_partner = row[col_indices.get('mixed_partner')] if 'mixed_partner' in col_indices else None
                    registration_date = row[col_indices.get('registration_date')] if 'registration_date' in col_indices else None
                    
                    cur.execute(f"""
                        INSERT INTO {table_name}
                        (license_id, singles_level, doubles_level, mixed_level, 
                         doubles_partner, mixed_partner, registration_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (license_id, singles_level, doubles_level, mixed_level, 
                          doubles_partner, mixed_partner, registration_date))
                    
                    migrated += 1
                except Exception as e:
                    print(f"    ⚠️  Error migrating row: {str(e)}")
            
            # Drop old table
            cur.execute(f"DROP TABLE {temp_table}")
            print(f"    ✅ Migrated {migrated}/{row_count} rows")
        
        conn.commit()
        conn.close()
        
        # Verify foreign keys work
        conn = sqlite3.connect(TOURNAMENTS_DB)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        for table_name in tables:
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cur.fetchall()]
            
            if 'license_id' in columns:
                # Check for orphaned references
                cur.execute(f"""
                    SELECT COUNT(*) FROM {table_name} r
                    WHERE NOT EXISTS (SELECT 1 FROM players p WHERE p.license_id = r.license_id)
                """)
                orphaned = cur.fetchone()[0]
                
                if orphaned > 0:
                    print(f"    ⚠️  {orphaned} orphaned player references in {table_name}")
        
        conn.close()
        
        print(f"\n✅ Normalization complete!")
        print(f"   - All denormalized columns removed")
        print(f"   - Foreign key constraints added")
        print(f"   - Backup: {backup_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print(f"⚠️  Restoring from backup: {backup_path}")
        shutil.copy2(backup_path, TOURNAMENTS_DB)
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Normalizing tournament_*_registrations tables")
    print("=" * 70)
    print()
    
    success = migrate_registrations_to_normalized()
    
    if success:
        print("\n✅ Migration successful - tournaments.db normalized")
    else:
        print("\n❌ Migration failed - tournaments.db restored from backup")
