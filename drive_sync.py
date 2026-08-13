"""
Dropbox sync module for SQLite databases
Syncs .db files to/from Dropbox for persistent storage
Includes auto-refresh of access tokens using refresh tokens
"""

import os
import logging
import dropbox
import requests
from dropbox.exceptions import ApiError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database files to sync
DB_FILES = [
    "players.db",
    "admin.db", 
    "point_rules.db",
    "tournaments.db"  # Single unified tournaments database
]

# Dropbox OAuth info
DROPBOX_APP_KEY = "2e0bvquyns4t5sb"
DROPBOX_APP_SECRET = os.getenv('DROPBOX_APP_SECRET', '9hljwc9w0c790w7')

class DropboxSync:
    """Handle Dropbox sync for SQLite databases"""
    
    def __init__(self):
        """Initialize Dropbox client"""
        self.dbx = None
        self.folder_path = None
        self.authenticated = False
        self._init_dropbox_client()
    
    def _refresh_access_token(self):
        """Refresh access token using refresh token"""
        try:
            refresh_token = os.getenv('DROPBOX_REFRESH_TOKEN')
            if not refresh_token:
                logger.warning("⚠️  DROPBOX_REFRESH_TOKEN not set - cannot auto-refresh")
                return False
            
            logger.info("🔄 Refreshing Dropbox access token...")
            
            response = requests.post('https://api.dropboxapi.com/oauth2/token', data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': DROPBOX_APP_KEY,
                'client_secret': DROPBOX_APP_SECRET
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                new_access_token = data.get('access_token')
                logger.info("✅ Access token refreshed successfully")
                
                # Update environment variable for this session
                os.environ['DROPBOX_ACCESS_TOKEN'] = new_access_token
                
                # Reinitialize with new token
                self.dbx = dropbox.Dropbox(new_access_token)
                return True
            else:
                logger.error(f"❌ Failed to refresh token: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error refreshing access token: {str(e)}")
            return False
    
    def _init_dropbox_client(self):
        """Initialize Dropbox client using access token, with auto-refresh on expiry"""
        try:
            # Get access token from environment
            access_token = os.getenv('DROPBOX_ACCESS_TOKEN')
            if not access_token:
                logger.error("❌ DROPBOX_ACCESS_TOKEN environment variable not set - sync DISABLED")
                logger.error("❌ Please set DROPBOX_ACCESS_TOKEN in Render environment variables")
                return False
            
            # Initialize Dropbox client
            self.dbx = dropbox.Dropbox(access_token)
            
            # Test connection
            try:
                self.dbx.users_get_current_account()
                logger.info("✅ Dropbox client initialized")
            except ApiError as e:
                if 'expired_access_token' in str(e):
                    logger.warning("⚠️  Access token expired, attempting refresh...")
                    if self._refresh_access_token():
                        logger.info("✅ Successfully refreshed token and reconnected")
                    else:
                        logger.error("❌ Could not refresh token - set DROPBOX_REFRESH_TOKEN in environment")
                        return False
                else:
                    raise
            
            # Get folder path from environment
            self.folder_path = os.getenv('DROPBOX_SYNC_FOLDER', '/BadmintonScrapPython-Databases')
            logger.info(f"✅ Using Dropbox folder: {self.folder_path}")
            
            # Ensure folder exists
            self._ensure_folder_exists()
            
            self.authenticated = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Dropbox client: {str(e)}")
            self.authenticated = False
            return False
    
    def _ensure_folder_exists(self):
        """Create folder in Dropbox if it doesn't exist"""
        try:
            self.dbx.files_get_metadata(self.folder_path)
            logger.info(f"✅ Dropbox folder exists: {self.folder_path}")
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                try:
                    self.dbx.files_create_folder_v2(self.folder_path)
                    logger.info(f"✅ Created Dropbox folder: {self.folder_path}")
                except Exception as create_err:
                    logger.error(f"❌ Failed to create folder: {str(create_err)}")
            else:
                logger.error(f"❌ Error checking folder: {str(e)}")
    
    def download_databases(self):
        """Download all .db files from Dropbox"""
        if not self.authenticated:
            logger.warning("⚠️  Dropbox not authenticated - skipping download")
            return False
        
        success_count = 0
        
        # Download root level databases
        for db_file in DB_FILES:
            if self._download_file(db_file):
                success_count += 1
        
        # All databases to sync are in DB_FILES list now
        # No need for separate tournament directory handling
        
        logger.info(f"✅ Downloaded {success_count} database files from Dropbox")
        return True
    
    def _download_file(self, filepath):
        """Download a single file from Dropbox"""
        try:
            dropbox_path = f"{self.folder_path}/{os.path.basename(filepath)}"
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            
            # Download file
            metadata, response = self.dbx.files_download(dropbox_path)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"✅ Downloaded: {filepath}")
            return True
            
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.debug(f"ℹ️  File not found in Dropbox (new file): {filepath}")
                return False
            else:
                logger.error(f"❌ Failed to download {filepath}: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to download {filepath}: {str(e)}")
            return False
    
    def upload_databases(self):
        """Upload all .db files to Dropbox"""
        if not self.authenticated:
            logger.warning("⚠️  Dropbox not authenticated - skipping upload")
            return False
        
        success_count = 0
        
        # Upload root level databases (including tournaments.db now)
        for db_file in DB_FILES:
            if os.path.exists(db_file):
                if self._upload_file(db_file):
                    success_count += 1
        
        logger.info(f"✅ Uploaded {success_count} database files to Dropbox")
        return True
    
    def _upload_file(self, filepath):
        """Upload a single file to Dropbox"""
        try:
            filename = os.path.basename(filepath)
            dropbox_path = f"{self.folder_path}/{filename}"
            
            with open(filepath, 'rb') as f:
                file_content = f.read()
            
            # Upload with overwrite
            self.dbx.files_upload(
                file_content,
                dropbox_path,
                mode=dropbox.files.WriteMode('overwrite', None),
                autorename=False
            )
            
            logger.info(f"✅ Uploaded: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to upload {filepath}: {str(e)}")
            return False


# Global sync instance
_sync = None

def init_sync():
    """Initialize Dropbox sync"""
    global _sync
    _sync = DropboxSync()
    return _sync

def get_sync():
    """Get the global sync instance"""
    global _sync
    if _sync is None:
        _sync = DropboxSync()
    return _sync

def download_all():
    """Download all databases from Dropbox"""
    logger.info("📥 Attempting to download databases from Dropbox...")
    sync = get_sync()
    return sync.download_databases()

def upload_all():
    """Upload all databases to Dropbox"""
    logger.info("📤 Attempting to upload databases to Dropbox...")
    sync = get_sync()
    return sync.upload_databases()
