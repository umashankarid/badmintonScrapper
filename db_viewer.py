"""
Database Viewer Module

Provides utilities for viewing and managing database contents in the admin panel.
Features:
- List all databases
- List tables in each database
- View table contents with pagination
- Export table data (JSON, CSV)
- Search in tables
- Database statistics
"""

import sqlite3
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Database paths
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(__file__))
PLAYERS_DB = os.path.join(DATA_DIR, "players.db")
TOURNAMENTS_DB = os.path.join(DATA_DIR, "tournaments.db")
ADMIN_DB = os.path.join(DATA_DIR, "admin.db")
POINT_RULES_DB = os.path.join(DATA_DIR, "point_rules.db")

DATABASES = [
    {"name": "players.db", "path": PLAYERS_DB, "description": "Global player registry with Badminton Sweden data"},
    {"name": "tournaments.db", "path": TOURNAMENTS_DB, "description": "Tournament metadata and player registrations"},
    {"name": "admin.db", "path": ADMIN_DB, "description": "Admin users, SMTP settings, reminder log"},
    {"name": "point_rules.db", "path": POINT_RULES_DB, "description": "Badminton scoring rules by level"},
]


def get_database_list():
    """
    Get list of all available databases
    
    Returns:
        list: Database information dictionaries
    """
    logger.info("📊 Fetching list of all databases")
    databases = []
    
    for db_info in DATABASES:
        db_path = db_info["path"]
        if os.path.exists(db_path):
            file_size = os.path.getsize(db_path)
            mod_time = datetime.fromtimestamp(os.path.getmtime(db_path)).isoformat()
            
            databases.append({
                "name": db_info["name"],
                "path": db_path,
                "description": db_info["description"],
                "exists": True,
                "size_bytes": file_size,
                "size_mb": round(file_size / (1024 * 1024), 2),
                "modified": mod_time
            })
            logger.debug(f"✅ Found database: {db_info['name']} ({file_size} bytes)")
        else:
            databases.append({
                "name": db_info["name"],
                "path": db_path,
                "description": db_info["description"],
                "exists": False,
                "size_bytes": 0,
                "size_mb": 0,
                "modified": None
            })
            logger.warning(f"⚠️  Database not found: {db_info['name']}")
    
    logger.info(f"✅ Found {len([d for d in databases if d['exists']])} databases")
    return databases


def get_tables_in_database(db_path):
    """
    Get list of tables in a database
    
    Args:
        db_path (str): Path to database file
    
    Returns:
        list: Table information dictionaries
    """
    logger.info(f"📋 Fetching tables from {os.path.basename(db_path)}")
    
    if not os.path.exists(db_path):
        logger.error(f"❌ Database not found: {db_path}")
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get all tables
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table'
            ORDER BY name
        """)
        
        tables = []
        for (table_name,) in cur.fetchall():
            # Get row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cur.fetchone()[0]
            
            # Get schema
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = cur.fetchall()
            
            tables.append({
                "name": table_name,
                "row_count": row_count,
                "column_count": len(columns),
                "columns": [{"name": col[1], "type": col[2]} for col in columns]
            })
            
            logger.debug(f"  📄 Table: {table_name} ({row_count} rows, {len(columns)} columns)")
        
        conn.close()
        logger.info(f"✅ Found {len(tables)} tables in {os.path.basename(db_path)}")
        return tables
    
    except Exception as e:
        logger.error(f"❌ Error fetching tables from {db_path}: {str(e)}")
        return []


def get_table_data(db_path, table_name, page=1, page_size=10, search=None):
    """
    Get table data with pagination and optional search
    
    Args:
        db_path (str): Path to database file
        table_name (str): Table name
        page (int): Page number (1-indexed)
        page_size (int): Rows per page
        search (str): Optional search term
    
    Returns:
        dict: Table data with pagination info
    """
    logger.info(f"📖 Fetching data from {os.path.basename(db_path)}.{table_name} (page {page})")
    
    if not os.path.exists(db_path):
        logger.error(f"❌ Database not found: {db_path}")
        return {"error": "Database not found"}
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cur = conn.cursor()
        
        # Get column info
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cur.fetchall()]
        
        # Count total rows
        if search:
            # Build search query
            search_conditions = " OR ".join([f"{col} LIKE ?" for col in columns])
            search_value = f"%{search}%"
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {search_conditions}", 
                       [search_value] * len(columns))
        else:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        
        total_rows = cur.fetchone()[0]
        
        # Calculate pagination
        total_pages = (total_rows + page_size - 1) // page_size
        offset = (page - 1) * page_size
        
        # Get data
        if search:
            search_conditions = " OR ".join([f"{col} LIKE ?" for col in columns])
            search_value = f"%{search}%"
            cur.execute(
                f"SELECT * FROM {table_name} WHERE {search_conditions} LIMIT ? OFFSET ?",
                [search_value] * len(columns) + [page_size, offset]
            )
        else:
            cur.execute(f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", (page_size, offset))
        
        rows = [dict(row) for row in cur.fetchall()]
        
        # Convert JSON strings to objects for display
        for row in rows:
            for col in columns:
                if col in row and row[col]:
                    try:
                        if isinstance(row[col], str) and row[col].startswith('{'):
                            row[col] = json.loads(row[col])
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON
        
        conn.close()
        
        logger.info(f"✅ Fetched {len(rows)} rows from {table_name} (page {page}/{total_pages})")
        logger.debug(f"  Columns: {', '.join(columns)}")
        
        return {
            "success": True,
            "table_name": table_name,
            "columns": columns,
            "rows": rows,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1
            },
            "search": search
        }
    
    except Exception as e:
        logger.error(f"❌ Error fetching data from {table_name}: {str(e)}")
        return {"error": str(e), "success": False}


def export_table_as_json(db_path, table_name, limit=None):
    """
    Export table data as JSON
    
    Args:
        db_path (str): Path to database file
        table_name (str): Table name
        limit (int): Maximum rows to export (None = all)
    
    Returns:
        str: JSON string
    """
    logger.info(f"📤 Exporting {table_name} from {os.path.basename(db_path)} as JSON")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get data
        if limit:
            cur.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
        else:
            cur.execute(f"SELECT * FROM {table_name}")
        
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        # Convert JSON strings to objects
        for row in rows:
            for key, value in row.items():
                if value and isinstance(value, str):
                    try:
                        if value.startswith('{') or value.startswith('['):
                            row[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
        
        json_data = json.dumps(rows, indent=2, default=str)
        logger.info(f"✅ Exported {len(rows)} rows from {table_name}")
        return json_data
    
    except Exception as e:
        logger.error(f"❌ Error exporting {table_name}: {str(e)}")
        return json.dumps({"error": str(e)})


def export_table_as_csv(db_path, table_name, limit=None):
    """
    Export table data as CSV
    
    Args:
        db_path (str): Path to database file
        table_name (str): Table name
        limit (int): Maximum rows to export (None = all)
    
    Returns:
        str: CSV string
    """
    logger.info(f"📤 Exporting {table_name} from {os.path.basename(db_path)} as CSV")
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get column names
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cur.fetchall()]
        
        # Get data
        if limit:
            cur.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
        else:
            cur.execute(f"SELECT * FROM {table_name}")
        
        rows = cur.fetchall()
        conn.close()
        
        # Create CSV
        csv_lines = [','.join(f'"{col}"' for col in columns)]
        for row in rows:
            csv_lines.append(','.join(
                f'"{val}"' if val is not None else '""'
                for val in row
            ))
        
        csv_data = '\n'.join(csv_lines)
        logger.info(f"✅ Exported {len(rows)} rows from {table_name}")
        return csv_data
    
    except Exception as e:
        logger.error(f"❌ Error exporting {table_name}: {str(e)}")
        return f"Error: {str(e)}"


def get_database_statistics():
    """
    Get statistics about all databases
    
    Returns:
        dict: Database statistics
    """
    logger.info("📊 Calculating database statistics")
    
    stats = {
        "total_size_bytes": 0,
        "total_size_mb": 0,
        "total_tables": 0,
        "total_rows": 0,
        "databases": []
    }
    
    for db_info in get_database_list():
        if not db_info["exists"]:
            continue
        
        db_path = db_info["path"]
        tables = get_tables_in_database(db_path)
        
        total_rows = sum(table["row_count"] for table in tables)
        
        db_stat = {
            "name": db_info["name"],
            "size_mb": db_info["size_mb"],
            "table_count": len(tables),
            "row_count": total_rows
        }
        
        stats["databases"].append(db_stat)
        stats["total_size_bytes"] += db_info["size_bytes"]
        stats["total_size_mb"] = round(stats["total_size_bytes"] / (1024 * 1024), 2)
        stats["total_tables"] += len(tables)
        stats["total_rows"] += total_rows
    
    logger.info(f"✅ Database statistics: {stats['total_tables']} tables, {stats['total_rows']} rows, {stats['total_size_mb']}MB")
    return stats
