#!/usr/bin/env python3
"""
Utility to encrypt Dropbox credentials for secure storage in Render
Run this locally to generate the encrypted credentials string
"""

from cryptography.fernet import Fernet
import base64
import hashlib
import sys

DROPBOX_APP_SECRET = '9hljwc9w0c790w7'  # Same as in drive_sync.py

def encrypt_credentials(email, password):
    """Encrypt email and password using the app secret as key"""
    # Create deterministic key from app secret
    key = base64.urlsafe_b64encode(
        hashlib.sha256(DROPBOX_APP_SECRET.encode()).digest()
    )
    
    cipher = Fernet(key)
    
    # Combine email and password
    credentials = f"{email}|{password}"
    
    # Encrypt
    encrypted = cipher.encrypt(credentials.encode()).decode()
    
    return encrypted

def main():
    print("=" * 70)
    print("🔐 Dropbox Credentials Encryption Utility")
    print("=" * 70)
    print()
    print("This will encrypt your Dropbox email and password for secure storage.")
    print()
    
    email = input("Enter your Dropbox email: ").strip()
    password = input("Enter your Dropbox password: ").strip()
    
    if not email or not password:
        print("❌ Email and password are required")
        sys.exit(1)
    
    print()
    print("🔄 Encrypting credentials...")
    encrypted = encrypt_credentials(email, password)
    
    print()
    print("=" * 70)
    print("✅ ENCRYPTED CREDENTIALS (copy this entire string)")
    print("=" * 70)
    print()
    print(encrypted)
    print()
    print("=" * 70)
    print("📝 Next steps:")
    print("1. Go to Render Dashboard → Your App → Environment")
    print("2. Add new variable:")
    print('   Name: DROPBOX_ENCRYPTED_CREDS')
    print(f'   Value: {encrypted}')
    print("3. Save and deploy")
    print("=" * 70)

if __name__ == "__main__":
    main()
