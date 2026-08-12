"""
Google Drive sync module for SQLite databases
Syncs .db files to/from Google Drive for persistent storage
"""

import os
import json
import logging
from pathlib import Path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database files to sync
DB_FILES = [
    "players.db",
    "admin.db", 
    "point_rules.db"
]

TOURNAMENTS_DIR = "tournaments"

class GoogleDriveSync:
    """Handle Google Drive sync for SQLite databases"""
    
    def __init__(self):
        """Initialize Google Drive API client"""
        self.drive_service = None
        self.folder_id = None
        self.authenticated = False
        self._init_drive_client()
    
    def _init_drive_client(self):
        """Initialize Google Drive client using service account credentials"""
        try:
            # Get credentials from environment variable
            creds_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
            if not creds_json:
                logger.warning("⚠️  GOOGLE_DRIVE_CREDENTIALS not set - sync disabled")
                return False
            
            # Parse service account credentials
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            
            # Build Drive service
            self.drive_service = build('drive', 'v3', credentials=credentials)
            
            # Get or create sync folder
            folder_id = os.getenv('GOOGLE_DRIVE_SYNC_FOLDER_ID')
            if folder_id:
                self.folder_id = folder_id
                logger.info(f"✅ Using existing Google Drive folder: {folder_id}")
            else:
                self._create_sync_folder()
            
            self.authenticated = True
            logger.info("✅ Google Drive client initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Drive client: {str(e)}")
            self.authenticated = False
            return False
    
    def _create_sync_folder(self):
        """Create a folder in Google Drive for syncing databases"""
        try:
            folder_metadata = {
                'name': 'BadmintonScrapPython-Databases',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            self.folder_id = folder['id']
            logger.info(f"✅ Created Google Drive folder: {self.folder_id}")
            logger.info(f"📝 Set GOOGLE_DRIVE_SYNC_FOLDER_ID={self.folder_id} in Render config")
            return self.folder_id
        except Exception as e:
            logger.error(f"❌ Failed to create sync folder: {str(e)}")
            return None
    
    def _get_file_id(self, filename):
        """Find file ID in Google Drive folder"""
        try:
            query = f"'{self.folder_id}' in parents and name='{filename}' and trashed=false"
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, modifiedTime)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
        except Exception as e:
            logger.error(f"❌ Error finding file {filename}: {str(e)}")
            return None
    
    def download_databases(self):
        """Download all .db files from Google Drive"""
        if not self.authenticated:
            logger.warning("⚠️  Google Drive not authenticated - skipping download")
            return False
        
        success_count = 0
        
        # Download root level databases
        for db_file in DB_FILES:
            if self._download_file(db_file):
                success_count += 1
        
        # Download tournament databases
        if os.path.exists(TOURNAMENTS_DIR):
            for tournament_file in os.listdir(TOURNAMENTS_DIR):
                if tournament_file.endswith('.db'):
                    if self._download_file(os.path.join(TOURNAMENTS_DIR, tournament_file)):
                        success_count += 1
        
        logger.info(f"✅ Downloaded {success_count} database files from Google Drive")
        return True
    
    def _download_file(self, filepath):
        """Download a single file from Google Drive"""
        try:
            file_id = self._get_file_id(os.path.basename(filepath))
            if not file_id:
                logger.debug(f"ℹ️  File not found in Drive (new file): {filepath}")
                return False
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            
            # Download file
            request = self.drive_service.files().get_media(fileId=file_id)
            with open(filepath, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            logger.info(f"✅ Downloaded: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download {filepath}: {str(e)}")
            return False
    
    def upload_databases(self):
        """Upload all .db files to Google Drive"""
        if not self.authenticated:
            logger.warning("⚠️  Google Drive not authenticated - skipping upload")
            return False
        
        success_count = 0
        
        # Upload root level databases
        for db_file in DB_FILES:
            if os.path.exists(db_file):
                if self._upload_file(db_file):
                    success_count += 1
        
        # Upload tournament databases
        if os.path.exists(TOURNAMENTS_DIR):
            for tournament_file in os.listdir(TOURNAMENTS_DIR):
                if tournament_file.endswith('.db'):
                    filepath = os.path.join(TOURNAMENTS_DIR, tournament_file)
                    if self._upload_file(filepath):
                        success_count += 1
        
        logger.info(f"✅ Uploaded {success_count} database files to Google Drive")
        return True
    
    def _upload_file(self, filepath):
        """Upload a single file to Google Drive"""
        try:
            filename = os.path.basename(filepath)
            file_id = self._get_file_id(filename)
            
            file_metadata = {'name': filename}
            media = MediaFileUpload(filepath, resumable=True)
            
            if file_id:
                # Update existing file
                request = self.drive_service.files().update(
                    fileId=file_id,
                    media_body=media,
                    fields='id'
                )
            else:
                # Create new file
                file_metadata['parents'] = [self.folder_id]
                request = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                )
            
            response = request.execute()
            logger.info(f"✅ Uploaded: {filepath} (ID: {response['id']})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to upload {filepath}: {str(e)}")
            return False


# Global sync instance
_sync = None

def init_sync():
    """Initialize Google Drive sync"""
    global _sync
    _sync = GoogleDriveSync()
    return _sync

def get_sync():
    """Get the global sync instance"""
    global _sync
    if _sync is None:
        _sync = GoogleDriveSync()
    return _sync

def download_all():
    """Download all databases from Google Drive"""
    sync = get_sync()
    return sync.download_databases()

def upload_all():
    """Upload all databases to Google Drive"""
    sync = get_sync()
    return sync.upload_databases()
