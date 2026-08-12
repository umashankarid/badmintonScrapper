#!/usr/bin/env python3
"""
Initialize umashankar1985@gmail.com as admin user
"""

import sqlite3
import os

ADMIN_DB = "admin.db"

def init_admin():
    """Initialize admin user"""
    
    if not os.path.exists(ADMIN_DB):
        print(f"❌ {ADMIN_DB} not found!")
        print("Make sure you're in the badmintonScrapPython directory")
        exit(1)
    
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    
    try:
        # Check if admins table has username column
        cur.execute("PRAGMA table_info(admins)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Delete existing admin if any
        cur.execute("DELETE FROM admins WHERE username=?", ("umashankar1985@gmail.com",))
        conn.commit()
        print("Cleared existing admin user if present")
        
        # Insert admin user
        cur.execute(
            "INSERT INTO admins (username) VALUES (?)",
            ("umashankar1985@gmail.com",)
        )
        conn.commit()
        
        print(f"✅ Admin user initialized successfully!")
        print(f"Username: umashankar1985@gmail.com")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    init_admin()
