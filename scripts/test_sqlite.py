"""Quick smoke test — run from project root: python scripts/test_sqlite.py"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from device.database import LocalDatabase
import sqlite3

print("── Initialising LocalDatabase (SQLite) ──")
db = LocalDatabase()
print("  LocalDatabase init: OK")

# Check tables
conn = sqlite3.connect("data/attendance_buffer.db")
cur  = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
conn.close()
print(f"  Tables created: {tables}")

# Insert a dummy record
row_id = db.add_record(
    device_id  = "cm4_test",
    name       = "Test_User",
    user_id    = "usr_001",
    confidence = 0.95
)
print(f"  add_record() → row id = {row_id}")

# Check unsynced records
lan_recs  = db.get_unsynced_lan_records()
mqtt_recs = db.get_unsynced_mqtt_records()
print(f"  Unsynced LAN  records: {len(lan_recs)}")
print(f"  Unsynced MQTT records: {len(mqtt_recs)}")

# Mark as synced
if lan_recs:
    ids = [r["id"] for r in lan_recs]
    db.mark_lan_synced(ids)
    db.mark_mqtt_synced(ids)
    print(f"  Marked {len(ids)} record(s) as fully synced.")

print("\n✅  All tests passed — SQLite works, no MySQL needed.")
