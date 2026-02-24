"""Quick smoke test for the users table."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from device.database import LocalDatabase

db = LocalDatabase()

# Test upsert
db.upsert_users([
    {"user_id": "101", "name": "Atharv Kulkarni"},
    {"user_id": "102", "name": "Ravi Sharma"},
])

# Test get
users = db.get_all_users()
print(f"Users in DB: {len(users)}")
for u in users:
    print(f"  {u['user_id']:8}  {u['name']}")

assert len(users) >= 2, "Expected at least 2 users"

# Test upsert updates name (conflict handling)
db.upsert_users([{"user_id": "101", "name": "Atharv K (Updated)"}])
users2 = db.get_all_users()
u101 = next((u for u in users2 if u["user_id"] == "101"), None)
assert u101 and "Updated" in u101["name"], "Upsert update failed"
print(f"Update test: {u101['name']}  ✓")

print("\nUsers table: ALL TESTS PASSED ✅")
