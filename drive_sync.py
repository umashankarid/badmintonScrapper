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

# Dropbox app-specific password (stored securely in Render)
DROPBOX_APP_PASSWORD = os.getenv('DROPBOX_APP_PASSWORD')
DROPBOX_EMAIL = os.getenv('DROPBOX_EMAIL')

class DropboxSync:
    """Handle Dropbox sync for SQLite databases"""
    
    def __init__(self):
        """Initialize Dropbox client"""
        self.dbx = None
        self.folder_path = None
        self.authenticated = False
        self._init_dropbox_client()
    
    def _generate_access_token(self):
        """Generate new access token using app-specific password"""
        try:
            if not DROPBOX_APP_PASSWORD or not DROPBOX_EMAIL:
                logger.warning("⚠️  DROPBOX_APP_PASSWORD or DROPBOX_EMAIL not set - cannot auto-generate token")
                return None
            
            logger.info("🔄 Generating new Dropbox access token...")
            
            # Use OAuth 2 password flow with app-specific password
            response = requests.post('https://api.dropboxapi.com/oauth2/token', 
                data={
                    'grant_type': 'password',
                    'username': DROPBOX_EMAIL,
                    'password': DROPBOX_APP_PASSWORD,
                    'client_id': DROPBOX_APP_KEY,
                    'client_secret': DROPBOX_APP_SECRET,
                    'scope': 'files.content.read files.content.write'
                }, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token')
                if new_token:
                    logger.info("✅ Successfully generated new access token")
                    # Update environment variable for this session
                    os.environ['DROPBOX_ACCESS_TOKEN'] = new_token
                    return new_token
                else:
                    logger.error(f"❌ No token in response: {data}")
                    return None
            else:
                logger.error(f"❌ Failed to generate token: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error generating access token: {str(e)}")
            return None
    
    def _init_dropbox_client(self):
        """Initialize Dropbox client using access token, with auto-generation on expiry"""
        try:
            # Get access token from environment
            access_token = os.getenv('DROPBOX_ACCESS_TOKEN')
            if not access_token:
                logger.error("❌ DROPBOX_ACCESS_TOKEN environment variable not set - sync DISABLED")
                logger.error("❌ To enable auto-token generation, set:")
                logger.error("   - DROPBOX_EMAIL: Your Dropbox email")
                logger.error("   - DROPBOX_APP_PASSWORD: App-specific password from Dropbox settings")
                return False
            
            # Initialize Dropbox client
            self.dbx = dropbox.Dropbox(access_token)
            
            # Test connection
            try:
                self.dbx.users_get_current_account()
                logger.info("✅ Dropbox client initialized with valid token")
            except ApiError as e:
                if 'expired_access_token' in str(e):
                    logger.warning("⚠️  Access token expired - attempting to generate new one...")
                    
                    # Try to auto-generate new token
                    new_token = self._generate_access_token()
                    if new_token:
                        # Reinitialize with new token
                        self.dbx = dropbox.Dropbox(new_token)
                        try:
                            self.dbx.users_get_current_account()
                            logger.info("✅ Successfully regenerated token and reconnected")
                        except ApiError as retry_error:
                            logger.error(f"❌ Failed to connect with regenerated token: {str(retry_error)}")
                            return False
                    else:
                        logger.error("❌ Auto-token generation failed")
                        logger.error("❌ Set DROPBOX_CREDENTIALS in Render or manually update DROPBOX_ACCESS_TOKEN")
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
