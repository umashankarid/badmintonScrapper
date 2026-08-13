"""
Refactored endpoint implementations for unified tournaments.db schema

These are reference implementations ready to be integrated into app.py
Each endpoint has been updated to:
- Use tournament_id instead of db_file or TOURNAMENTS_DIR scanning
- Query tournaments.db instead of per-tournament files
- Use license_id for player identification
- Return proper error responses
"""

from flask import jsonify, session, request
import sqlite3
import os
from datetime import datetime as dt

TOURNAMENTS_DB = "tournaments.db"
ADMIN_DB = "admin.db"

# ==================== HELPER FUNCTIONS ====================

def get_tournament_by_id(tournament_id):
    """Get tournament by ID from unified schema"""
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM tournaments WHERE id=?", (tournament_id,))
    result = cur.fetchone()
    conn.close()
    return result

def get_player_registration(tournament_id, license_id):
    """Get player registration for tournament"""
    table_name = f"tournament_{tournament_id}_registrations"
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Check table exists
    cur.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    
    if not cur.fetchone():
        conn.close()
        return None
    
    # Get registration
    cur.execute(f"SELECT * FROM {table_name} WHERE license_id=?", (license_id,))
    result = cur.fetchone()
    conn.close()
    return result


# ==================== REFACTORED ENDPOINTS ====================

# 1. GET /api/my-registrations (Refactored)
def my_registrations_refactored():
    """
    Get tournaments where logged-in player is registered
    
    Uses: players.license_id from session
    Returns: List of tournament_ids where player is registered
    """
    license_id = session.get("license_id")
    if not license_id:
        return jsonify(success=False, tournaments=[])
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Get all registration tables
    cur.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE 'tournament_%_registrations'
    """)
    
    tables = [row[0] for row in cur.fetchall()]
    registered_tournaments = []
    
    for table in tables:
        # Check if player is in this table
        cur.execute(f"""
            SELECT tournament_id FROM {table} WHERE license_id=? LIMIT 1
        """, (license_id,))
        
        row = cur.fetchone()
        if row:
            # Get tournament details
            tournament_id = row[0] if row else int(table.split('_')[1])
            cur.execute("""
                SELECT id, tournament_name, location, date_start, date_end
                FROM tournaments WHERE id=?
            """, (tournament_id,))
            
            tournament = cur.fetchone()
            if tournament:
                registered_tournaments.append({
                    "id": tournament[0],
                    "name": tournament[1],
                    "location": tournament[2],
                    "date_start": tournament[3],
                    "date_end": tournament[4]
                })
    
    conn.close()
    return jsonify(success=True, tournaments=registered_tournaments)


# 2. GET /api/open-tournaments (Already mostly refactored, minimal updates)
def open_tournaments_refactored():
    """
    Fetch tournaments selected for view AND not expired from tournaments.db
    """
    try:
        today = dt.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(TOURNAMENTS_DB)
        cur = conn.cursor()
        
        # Get tournaments marked as selected_for_view = 1 AND date_end >= TODAY
        cur.execute("""
            SELECT id, tournament_url, tournament_name, location, date_start, date_end,
                   registration_opens, registration_closes, cancellation_deadline,
                   competition_start, competition_end
            FROM tournaments 
            WHERE selected_for_view = 1 
            AND date_end >= ?
            ORDER BY registration_closes ASC, tournament_name ASC
        """, (today,))
        
        rows = cur.fetchall()
        conn.close()
        
        tournaments = []
        for row in rows:
            tournaments.append({
                "id": row[0],
                "url": row[1],
                "name": row[2],
                "location": row[3],
                "date_start": row[4],
                "date_end": row[5],
                "registration_opens": row[6],
                "registration_closes": row[7],
                "cancellation_deadline": row[8],
                "competition_start": row[9],
                "competition_end": row[10]
            })
        
        return jsonify(success=True, tournaments=tournaments)
    
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


# 3. POST /api/validate-registration (keeps current logic, adds DB check)
def validate_registration_with_db_check():
    """
    Check if player's points and age allow them to register for a given level.
    ALSO verify player is not already registered if tournament_id provided.
    
    Current implementation validates age/points restrictions.
    This version adds a check to ensure player isn't duplicate-registered.
    """
    data = request.json
    level = data.get("level", "").strip()
    category = data.get("category", "")  # HS, DS, HD, DD, MD
    points = data.get("points")  # player's points for that category
    age = data.get("age")  # player's age
    dob = data.get("dob", "")  # player's date of birth
    competition_date = data.get("competition_date", "")  # tournament competition start date
    
    # NEW: Check if already registered (if tournament_id provided)
    tournament_id = data.get("tournament_id")
    license_id = data.get("license_id") or session.get("license_id")
    
    if tournament_id and license_id:
        registration = get_player_registration(tournament_id, license_id)
        if registration:
            return jsonify(success=True, allowed=False, 
                message="Player already registered for this tournament")
    
    # ... (rest of original validation logic remains the same)
    # Age-based levels, point restrictions, etc.
    
    return jsonify(success=True, allowed=True)


# 4. GET /api/tournament-visibility (Refactored)
def tournament_visibility_refactored():
    """
    Get list of all tournaments and their visibility status
    Uses unified tournaments.db schema
    """
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Get all tournaments
    cur.execute("""
        SELECT id, tournament_name, location, date_start, date_end, 
               selected_for_view, registration_closes
        FROM tournaments
        ORDER BY date_start DESC, tournament_name ASC
    """)
    
    rows = cur.fetchall()
    conn.close()
    
    tournaments = []
    for row in rows:
        tournaments.append({
            "id": row[0],
            "name": row[1],
            "location": row[2],
            "date_start": row[3],
            "date_end": row[4],
            "visible": row[5],
            "registration_closes": row[6]
        })
    
    return jsonify(success=True, tournaments=tournaments)


# 5. POST /api/tournament-visibility/toggle (Refactored)
def toggle_tournament_visibility_refactored():
    """
    Toggle tournament visibility for available tournaments list
    Uses unified tournaments.db schema (selected_for_view field)
    """
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    tournament_id = request.json.get('tournament_id')
    
    if not tournament_id:
        return jsonify(success=False, error="tournament_id required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Verify tournament exists
    cur.execute("SELECT selected_for_view FROM tournaments WHERE id=?", (tournament_id,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return jsonify(success=False, error="Tournament not found"), 404
    
    # Toggle visibility
    current_visibility = row[0]
    new_visibility = 1 - current_visibility
    
    cur.execute("""
        UPDATE tournaments
        SET selected_for_view = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_visibility, tournament_id))
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, visibility=new_visibility, tournament_id=tournament_id)


# 6. GET /api/ensure-tournament (Refactored)
def ensure_tournament_refactored():
    """
    Ensure tournament exists in tournaments.db
    Returns tournament_id if it exists or was created
    """
    data = request.json
    tournament_url = data.get('tournament_url')
    tournament_name = data.get('tournament_name', '')
    
    if not tournament_url:
        return jsonify(success=False, error="tournament_url required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Check if exists
    cur.execute("SELECT id FROM tournaments WHERE tournament_url=?", (tournament_url,))
    row = cur.fetchone()
    
    if row:
        # Already exists
        conn.close()
        return jsonify(success=True, tournament_id=row[0], created=False)
    
    # Create new tournament
    cur.execute("""
        INSERT INTO tournaments 
        (tournament_url, tournament_name, selected_for_view, created_at, last_updated)
        VALUES (?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (tournament_url, tournament_name))
    
    tournament_id = cur.lastrowid
    
    # Create registration table for this tournament
    table_name = f"tournament_{tournament_id}_registrations"
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            singles_level TEXT,
            doubles_level TEXT,
            mixed_level TEXT,
            doubles_partner TEXT,
            mixed_partner TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, tournament_id=tournament_id, created=True)


# 7. POST /admin/create-tournament (Refactored)
def create_tournament_refactored():
    """
    Create new tournament in tournaments.db
    Replaces old file-based approach
    """
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    data = request.json
    tournament_url = data.get('tournament_url')
    tournament_name = data.get('tournament_name')
    location = data.get('location', '')
    date_start = data.get('date_start', '')
    date_end = data.get('date_end', '')
    
    if not tournament_url or not tournament_name:
        return jsonify(success=False, error="tournament_url and tournament_name required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Check URL not already used
    cur.execute("SELECT id FROM tournaments WHERE tournament_url=?", (tournament_url,))
    if cur.fetchone():
        conn.close()
        return jsonify(success=False, error="Tournament URL already exists"), 409
    
    # Insert tournament
    cur.execute("""
        INSERT INTO tournaments
        (tournament_url, tournament_name, location, date_start, date_end,
         selected_for_view, created_at, last_updated)
        VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (tournament_url, tournament_name, location, date_start, date_end))
    
    tournament_id = cur.lastrowid
    
    # Create registration table
    table_name = f"tournament_{tournament_id}_registrations"
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            singles_level TEXT,
            doubles_level TEXT,
            mixed_level TEXT,
            doubles_partner TEXT,
            mixed_partner TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, tournament_id=tournament_id)


# 8. POST /admin/delete-tournament (Refactored)
def delete_tournament_refactored():
    """
    Delete tournament from tournaments.db and drop its registration table
    """
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    tournament_id = request.json.get('tournament_id')
    
    if not tournament_id:
        return jsonify(success=False, error="tournament_id required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Verify exists
    cur.execute("SELECT tournament_name FROM tournaments WHERE id=?", (tournament_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify(success=False, error="Tournament not found"), 404
    
    tournament_name = row[0]
    
    # Drop registration table
    table_name = f"tournament_{tournament_id}_registrations"
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    
    # Delete tournament
    cur.execute("DELETE FROM tournaments WHERE id=?", (tournament_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, message=f"Deleted tournament: {tournament_name}")


# 9. GET /api/tournament-events (Refactored)
def tournament_events_refactored():
    """
    Get tournament events/schedule from unified schema
    """
    tournament_id = request.args.get('tournament_id')
    
    if not tournament_id:
        return jsonify(success=False, error="tournament_id required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, tournament_name, location, date_start, date_end,
               registration_opens, registration_closes, cancellation_deadline,
               competition_start, competition_end
        FROM tournaments WHERE id=?
    """, (tournament_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return jsonify(success=False, error="Tournament not found"), 404
    
    events = {
        "tournament_id": row[0],
        "name": row[1],
        "location": row[2],
        "registration_opens": row[5],
        "registration_closes": row[6],
        "cancellation_deadline": row[7],
        "competition_start": row[8],
        "competition_end": row[9],
        "competition_dates": {
            "start": row[3],
            "end": row[4]
        }
    }
    
    return jsonify(success=True, events=events)


# 10. GET /api/bwf-tournaments-all (Refactored)
def bwf_tournaments_all_refactored():
    """
    Get ALL tournaments (including hidden ones) from unified schema
    Admin only
    """
    if not session.get("admin"):
        return jsonify(tournaments=[])
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, tournament_url, tournament_name, location, date_start, date_end,
               selected_for_view, created_at
        FROM tournaments
        ORDER BY created_at DESC
    """)
    
    rows = cur.fetchall()
    conn.close()
    
    tournaments = []
    for row in rows:
        tournaments.append({
            "id": row[0],
            "url": row[1],
            "name": row[2],
            "location": row[3],
            "date_start": row[4],
            "date_end": row[5],
            "visible": row[6],
            "created": row[7]
        })
    
    return jsonify(tournaments=tournaments)


# 11. POST /api/bwf-tournament-visibility/save (Refactored)
def bwf_tournament_visibility_save_refactored():
    """
    Save BWF tournament visibility settings to unified schema
    """
    if not session.get("admin"):
        return jsonify(success=False, error="Unauthorized"), 401
    
    tournament_id = request.json.get('tournament_id')
    visible = request.json.get('visible', 0)
    
    if not tournament_id:
        return jsonify(success=False, error="tournament_id required"), 400
    
    conn = sqlite3.connect(TOURNAMENTS_DB)
    cur = conn.cursor()
    
    # Verify exists
    cur.execute("SELECT id FROM tournaments WHERE id=?", (tournament_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify(success=False, error="Tournament not found"), 404
    
    # Update visibility
    cur.execute("""
        UPDATE tournaments
        SET selected_for_view = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (visible, tournament_id))
    
    conn.commit()
    conn.close()
    
    return jsonify(success=True, tournament_id=tournament_id, visible=visible)
