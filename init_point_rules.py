import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "point_rules.db")

def init_point_rules():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS point_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            klass TEXT NOT NULL,
            hs_min INTEGER,
            hs_max INTEGER,
            ds_min INTEGER,
            ds_max INTEGER,
            hd_min INTEGER,
            hd_max INTEGER,
            dd_min INTEGER,
            dd_max INTEGER,
            md_min INTEGER,
            md_max INTEGER
        )
    """)
    # Check if already populated
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM point_rules")
    if cur.fetchone()[0] == 0:
        # Elit: > threshold (no max)
        # A: range
        # B: range
        # C: < threshold (no min)
        # D: < threshold (no min)
        rules = [
            ("Elit", 3500, None, 2250, None, 3500, None, 2250, None, 3000, None),
            ("A", 1300, 7000, 1100, 6000, 1300, 7000, 1100, 6000, 1100, 5000),
            ("B", 300, 1700, 200, 1500, 300, 1700, 200, 1500, 200, 1500),
            ("C", 0, 500, 0, 400, 0, 500, 0, 400, 0, 400),
            ("D", 0, 100, 0, 100, 0, 100, 0, 100, 0, 100),
        ]
        conn.executemany(
            "INSERT INTO point_rules (klass, hs_min, hs_max, ds_min, ds_max, hd_min, hd_max, dd_min, dd_max, md_min, md_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rules
        )
        conn.commit()
        print("Point rules initialized.")
    else:
        print("Point rules already exist.")
    conn.close()

if __name__ == "__main__":
    init_point_rules()
