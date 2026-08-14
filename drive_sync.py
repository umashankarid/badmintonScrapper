"""
Dropbox sync module for SQLite databases
Syncs .db files to/from Dropbox for persistent storage
Uses refresh token for reliable auto-renewal of access tokens
"""

import os
import logging
import dropbox
import requests
from dropbox.exceptions import ApiError, AuthError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database files to sync (root level only)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILES = [
    os.path.join(DATA_DIR, "players.db"),
    os.path.join(DATA_DIR, "admin.db"),
    os.path.join(DATA_DIR, "point_rules.db"),
    os.path.join(DATA_DIR, "tournaments.db")
]

# Dropbox OAuth info
DROPBOX_APP_KEY = os.getenv('DROPBOX_APP_KEY', '2e0bvquyns4t5sb')
DROPBOX_APP_SECRET = os.getenv('DROPBOX_APP_SECRET', '9hljwc9w0c790w7')
DROPBOX_REFRESH_TOKEN = os.getenv('DROPBOX_REFRESH_TOKEN', '')


class DropboxSync:
    """Handle Dropbox sync for SQLite databases using refresh token"""
    
    def __init__(self):
        """Initialize Dropbox client"""
        self.dbx = None
        self.folder_path = None
        self.authenticated = False
        self._init_dropbox_client()
    
    def _refresh_access_token(self):
        """
        Generate a new access token using the refresh token.
        Refresh tokens are long-lived and never expire unless revoked.
        """
        if not DROPBOX_REFRESH_TOKEN:
            logger.error("❌ DROPBOX_REFRESH_TOKEN not set - cannot refresh access token")
            return None
        
        try:
            logger.info("🔄 Refreshing Dropbox access token...")
            response = requests.post('https://api.dropboxapi.com/oauth2/token', data={
                'grant_type': 'refresh_token',
                'refresh_token': DROPBOX_REFRESH_TOKEN,
                'client_id': DROPBOX_APP_KEY,
                'client_secret': DROPBOX_APP_SECRET
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token')
                if new_token:
                    logger.info("✅ Successfully refreshed access token")
                    os.environ['DROPBOX_ACCESS_TOKEN'] = new_token
                    return new_token
                else:
                    logger.error(f"❌ No access_token in response: {data}")
                    return None
            else:
                logger.error(f"❌ Token refresh failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error refreshing access token: {str(e)}")
            return None
    
    def _init_dropbox_client(self):
        """Initialize Dropbox client. Uses refresh token to get/renew access token."""
        try:
            # Method 1: Use refresh token directly with Dropbox SDK (preferred)
            if DROPBOX_REFRESH_TOKEN:
                try:
                    self.dbx = dropbox.Dropbox(
                        oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
                        app_key=DROPBOX_APP_KEY,
                        app_secret=DROPBOX_APP_SECRET
                    )
                    # Test connection (this will auto-refresh if needed)
                    self.dbx.users_get_current_account()
                    logger.info("✅ Dropbox client initialized with refresh token")
                    
                    self.folder_path = os.getenv('DROPBOX_SYNC_FOLDER', '/BadmintonScrapPython-Databases')
                    logger.info(f"✅ Using Dropbox folder: {self.folder_path}")
                    self._ensure_folder_exists()
                    self.authenticated = True
                    return True
                except AuthError as e:
                    logger.error(f"❌ Refresh token auth failed: {str(e)}")
                    logger.error("❌ The refresh token may be revoked. Generate a new one.")
                    return False
                except Exception as e:
                    logger.warning(f"⚠️  Refresh token SDK init failed: {str(e)}, trying access token...")
            
            # Method 2: Fall back to direct access token
            access_token = os.getenv('DROPBOX_ACCESS_TOKEN')
            if not access_token:
                # Try to get one from refresh token
                if DROPBOX_REFRESH_TOKEN:
                    access_token = self._refresh_access_token()
                
                if not access_token:
                    logger.error("❌ No DROPBOX_REFRESH_TOKEN or DROPBOX_ACCESS_TOKEN set - sync DISABLED")
                    logger.error("❌ See DROPBOX_TOKEN_STEPS.md for setup instructions")
                    return False
            
            # Initialize with access token
            self.dbx = dropbox.Dropbox(access_token)
            
            # Test connection
            try:
                self.dbx.users_get_current_account()
                logger.info("✅ Dropbox client initialized with access token")
            except AuthError as e:
                if 'expired_access_token' in str(e) or 'invalid_access_token' in str(e):
                    logger.warning("⚠️  Access token expired - attempting refresh...")
                    new_token = self._refresh_access_token()
                    if new_token:
                        self.dbx = dropbox.Dropbox(new_token)
                        self.dbx.users_get_current_account()
                        logger.info("✅ Reconnected with refreshed token")
                    else:
                        logger.error("❌ Token refresh failed - sync DISABLED")
                        return False
                else:
                    raise
            
            self.folder_path = os.getenv('DROPBOX_SYNC_FOLDER', '/BadmintonScrapPython-Databases')
            logger.info(f"✅ Using Dropbox folder: {self.folder_path}")
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
        
        for db_file in DB_FILES:
            if self._download_file(db_file):
                success_count += 1
        
        logger.info(f"✅ Downloaded {success_count} database files from Dropbox")
        return True
    
    def _download_file(self, filepath):
        """Download a single file from Dropbox"""
        try:
            dropbox_path = f"{self.folder_path}/{os.path.basename(filepath)}"
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            
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
        """Upload all .db files to Dropbox (overwrite)"""
        if not self.authenticated:
            logger.warning("⚠️  Dropbox not authenticated - skipping upload")
            return False
        
        success_count = 0
        
        for db_file in DB_FILES:
            if os.path.exists(db_file):
                if self._upload_file(db_file):
                    success_count += 1
            else:
                logger.debug(f"ℹ️  File not found locally: {db_file}")
        
        logger.info(f"✅ Uploaded {success_count} database files to Dropbox")
        return True
    
    def _upload_file(self, filepath):
        """Upload a single file to Dropbox"""
        try:
            filename = os.path.basename(filepath)
            dropbox_path = f"{self.folder_path}/{filename}"
            
            with open(filepath, 'rb') as f:
                file_content = f.read()
            
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
