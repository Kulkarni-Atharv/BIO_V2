
import logging

logger = logging.getLogger("ServerDB")

import sqlite3
import datetime
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config import SERVER_DB_PATH

class ServerDatabase:
    def __init__(self, connection_string=None):
        # connection_string argument is kept for compatibility but ignored in favor of SERVER_DB_PATH
        self.db_path = SERVER_DB_PATH
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS AttendanceLogs (
                        ID INTEGER PRIMARY KEY AUTOINCREMENT,
                        DeviceID TEXT,
                        Name TEXT,
                        Timestamp DATETIME,
                        ReceivedAt DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def insert_attendance(self, device_id, name, timestamp):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                dt = datetime.datetime.fromtimestamp(timestamp)
                
                cursor.execute("INSERT INTO AttendanceLogs (DeviceID, Name, Timestamp) VALUES (?, ?, ?)", 
                               (device_id, name, dt))
                conn.commit()
                logger.info(f"Saved to DB: {name} from {device_id}")
            return True
        except Exception as e:
            logger.error(f"Database insert error: {e}")
            return False
