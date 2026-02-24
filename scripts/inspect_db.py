"""Inspect the current attendance_buffer.db schema."""
import sqlite3, os

db_path = os.path.join("data", "attendance_buffer.db")
if not os.path.exists(db_path):
    print("DB file does not exist yet.")
else:
    conn = sqlite3.connect(db_path)
    print("=== Tables ===")
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        tname = row[0]
        print(f"\nTable: {tname}")
        for col in conn.execute(f"PRAGMA table_info({tname})"):
            print(f"  col {col[0]}: {col[1]} ({col[2]})")
    conn.close()
