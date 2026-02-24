"""
server/database.py
──────────────────
SQLite-backed database for the LAN receiver PC.
No MySQL, no external services — just a local .db file in data/.
"""

import sqlite3
import os
import sys
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config import SERVER_DB_PATH

logger = logging.getLogger("ServerDB")


def _get_conn():
    os.makedirs(os.path.dirname(SERVER_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(SERVER_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class ServerDatabase:
    def __init__(self, connection_string=None):   # connection_string kept for compat
        self._init_db()

    def _init_db(self):
        with _get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS attendance_log (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id                TEXT,
                    user_id                  TEXT,
                    name                     TEXT,
                    punch_time               TEXT,
                    punch_date               TEXT,
                    punch_clock              TEXT,
                    punch_type               TEXT,
                    attendance_status        TEXT,
                    late_minutes             INTEGER DEFAULT 0,
                    early_departure_minutes  INTEGER DEFAULT 0,
                    overtime_minutes         INTEGER DEFAULT 0,
                    confidence               REAL,
                    received_at              TEXT DEFAULT (datetime('now','localtime'))
                );
            """)
        logger.info("Server SQLite DB ready: %s", SERVER_DB_PATH)

    def insert_attendance(self, record: dict) -> bool:
        try:
            with _get_conn() as conn:
                conn.execute("""
                    INSERT INTO attendance_log
                        (device_id, user_id, name, punch_time, punch_date, punch_clock,
                         punch_type, attendance_status, late_minutes,
                         early_departure_minutes, overtime_minutes, confidence)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    record.get("device_id"),
                    record.get("user_id"),
                    record.get("name"),
                    record.get("punch_time"),
                    record.get("punch_date"),
                    record.get("punch_clock"),
                    record.get("punch_type"),
                    record.get("attendance_status"),
                    record.get("late_minutes", 0),
                    record.get("early_departure_minutes", 0),
                    record.get("overtime_minutes", 0),
                    record.get("confidence"),
                ))
            return True
        except Exception as e:
            logger.error("DB insert failed: %s", e)
            return False

    def get_all_records(self):
        with _get_conn() as conn:
            cur = conn.execute("SELECT * FROM attendance_log ORDER BY punch_time DESC")
            return [dict(r) for r in cur.fetchall()]
