#!/usr/bin/env python3
"""
Reset admin user credentials in admin.db
Run this if you forgot the admin password
"""

import sqlite3
import os
import hashlib

ADMIN_DB = "admin.db"

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def reset_admin():
    """Reset admin user to default credentials"""
    
    # Connect to admin.db
    conn = sqlite3.connect(ADMIN_DB)
    cur = conn.cursor()
    
    try:
        # Check if admins table has password column
        cur.execute("PRAGMA table_info(admins)")
        columns = [col[1] for col in cur.fetchall()]
        print(f"Admins table columns: {columns}")
        
        # If password column doesn't exist, add it
        if 'password' not in columns:
            print("Adding password column to admins table...")
            cur.execute("ALTER TABLE admins ADD COLUMN password TEXT")
            conn.commit()
        
        # Delete existing admin user if exists
        cur.execute("DELETE FROM admins WHERE username=?", ("admin",))
        conn.commit()
        print("Deleted existing admin user")
        
        # Insert new admin user with default password
        default_password = "admin123"
        hashed_password = hash_password(default_password)
        
        cur.execute(
            "INSERT INTO admins (username, password) VALUES (?, ?)",
            ("admin", hashed_password)
        )
        conn.commit()
        
        print(f"✅ Admin user reset successfully!")
        print(f"Username: admin")
        print(f"Password: {default_password}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    # Check if admin.db exists
    if not os.path.exists(ADMIN_DB):
        print(f"❌ {ADMIN_DB} not found!")
        print("Make sure you're in the badmintonScrapPython directory")
        exit(1)
    
    reset_admin()
