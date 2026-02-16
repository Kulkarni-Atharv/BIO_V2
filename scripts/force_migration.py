import sys
import os
import mysql.connector

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config import MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, MYSQL_PORT

def force_migration():
    print(f"Connecting to {MYSQL_HOST}:{MYSQL_PORT}...")
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            port=MYSQL_PORT
        )
        print("Connected.")
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    cursor = conn.cursor()
    
    # Check Columns
    # Re-fetch columns
    cursor.execute("DESCRIBE attendance_log")
    columns = [row[0] for row in cursor.fetchall()]
    print(f"Current columns: {columns}")
    
    # 1. user_id
    if 'user_id' not in columns:
        print("Adding 'user_id'...")
        try:
            cursor.execute("ALTER TABLE attendance_log ADD COLUMN user_id VARCHAR(100) AFTER id")
        except Exception as e:
            print(f"Failed to add user_id: {e}")
            cursor.execute("ALTER TABLE attendance_log ADD COLUMN user_id VARCHAR(100)")
            
    # 2. punch_time (Original schema had 'timestamp' double)
    if 'punch_time' not in columns:
        print("Adding 'punch_time'...")
        try:
            # Try to add after device_id
            cursor.execute("ALTER TABLE attendance_log ADD COLUMN punch_time DATETIME AFTER device_id")
        except:
             cursor.execute("ALTER TABLE attendance_log ADD COLUMN punch_time DATETIME")

    # 3. punch_date
    if 'punch_date' not in columns:
        print("Adding 'punch_date'...")
        cursor.execute("ALTER TABLE attendance_log ADD COLUMN punch_date DATE") # Append to end to be safe

    # 4. punch_clock
    if 'punch_clock' not in columns:
        print("Adding 'punch_clock'...")
        cursor.execute("ALTER TABLE attendance_log ADD COLUMN punch_clock TIME")

    # 5. punch_type
    if 'punch_type' not in columns:
         print("Adding 'punch_type'...")
         cursor.execute("ALTER TABLE attendance_log ADD COLUMN punch_type ENUM('IN','OUT')")

    # 6. shift_id
    if 'shift_id' not in columns:
         print("Adding 'shift_id'...")
         cursor.execute("ALTER TABLE attendance_log ADD COLUMN shift_id INT")
         # Add FK constraint?
         try:
             cursor.execute("ALTER TABLE attendance_log ADD CONSTRAINT fk_shift FOREIGN KEY (shift_id) REFERENCES shifts(id)")
         except Exception as e:
             print(f"FK Error (maybe shifts table missing?): {e}")

    # 7. Status columns
    new_cols = [
        ("attendance_status", "VARCHAR(50) DEFAULT 'Present'"),
        ("late_minutes", "INT DEFAULT 0"),
        ("early_departure_minutes", "INT DEFAULT 0"),
        ("overtime_minutes", "INT DEFAULT 0"),
        ("confidence", "FLOAT")
    ]
    
    for col_name, col_def in new_cols:
        if col_name not in columns:
             print(f"Adding '{col_name}'...")
             cursor.execute(f"ALTER TABLE attendance_log ADD COLUMN {col_name} {col_def}")

    conn.commit()
    print("Migration Check Completed.")

    conn.close()

if __name__ == "__main__":
    force_migration()
