"""
device/database.py
──────────────────
Local SQLite database for the CM4 / Raspberry Pi.
Works completely OFFLINE — no MySQL or external server required.

Schema
  shifts         — shift definitions (General Shift by default)
  attendance_log — every punch-in / punch-out record
  users          — employee master list synced from the cloud dashboard

Sync Flags (per record, independent)
  lan_synced  = 1  once the record has been POSTed to the LAN PC
  mqtt_synced = 1  once the record has been published to EMQX MQTT
"""

import sqlite3
import time
import os
import sys
import logging
from datetime import datetime, timedelta, date, time as dt_time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config import DB_PATH

logger = logging.getLogger("Database")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_conn():
    """Return a new SQLite connection with row-factory set."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent readers
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Main Class ───────────────────────────────────────────────────────────────

class LocalDatabase:
    def __init__(self):
        self._init_db()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_db(self):
        """Create tables if missing, then run schema migration for older DBs."""
        with _get_conn() as conn:
            # ── Create tables ─────────────────────────────────────────────────
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS shifts (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    shift_name          TEXT    NOT NULL,
                    start_time          TEXT    NOT NULL,
                    end_time            TEXT    NOT NULL,
                    late_grace_mins     INTEGER DEFAULT 15,
                    half_day_min_hours  REAL    DEFAULT 4.0,
                    overtime_start_mins INTEGER DEFAULT 30,
                    created_at          TEXT    DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS attendance_log (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id                  TEXT,
                    name                     TEXT,
                    device_id                TEXT,
                    punch_time               TEXT,
                    punch_date               TEXT,
                    punch_clock              TEXT,
                    punch_type               TEXT CHECK(punch_type IN ('IN','OUT')),
                    shift_id                 INTEGER REFERENCES shifts(id),
                    attendance_status        TEXT    DEFAULT 'Present',
                    late_minutes             INTEGER DEFAULT 0,
                    early_departure_minutes  INTEGER DEFAULT 0,
                    overtime_minutes         INTEGER DEFAULT 0,
                    confidence               REAL,
                    lan_synced               INTEGER DEFAULT 0,
                    mqtt_synced              INTEGER DEFAULT 0,
                    created_at               TEXT    DEFAULT (datetime('now','localtime'))
                );
            """)

            # ── Users table (employee master list from dashboard) ─────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id   TEXT PRIMARY KEY,
                    name      TEXT NOT NULL,
                    synced_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)

            # ── Seed default shift ────────────────────────────────────────────
            cur = conn.execute("SELECT COUNT(*) FROM shifts")
            if cur.fetchone()[0] == 0:
                conn.execute("""
                    INSERT INTO shifts (shift_name, start_time, end_time, late_grace_mins)
                    VALUES ('General Shift', '09:00:00', '18:00:00', 15)
                """)
                logger.info("Created default 'General Shift'.")

            # ── Schema migration (add columns missing from older DBs) ──────────
            cur = conn.execute("PRAGMA table_info(attendance_log)")
            existing_cols = {row[1] for row in cur.fetchall()}

            new_columns = {
                "user_id":                  "TEXT",
                "punch_time":               "TEXT",     # replaces legacy 'timestamp' REAL
                "punch_date":               "TEXT",
                "punch_clock":              "TEXT",
                "punch_type":               "TEXT",
                "shift_id":                 "INTEGER",
                "attendance_status":        "TEXT    DEFAULT 'Present'",
                "late_minutes":             "INTEGER DEFAULT 0",
                "early_departure_minutes":  "INTEGER DEFAULT 0",
                "overtime_minutes":         "INTEGER DEFAULT 0",
                "confidence":               "REAL",
                "lan_synced":               "INTEGER DEFAULT 0",
                "mqtt_synced":              "INTEGER DEFAULT 0",
                "created_at":               "TEXT",
            }
            for col, col_type in new_columns.items():
                if col not in existing_cols:
                    conn.execute(
                        f"ALTER TABLE attendance_log ADD COLUMN {col} {col_type}"
                    )
                    logger.info("Migration: added column '%s'.", col)

            # Backfill punch_time from legacy Unix 'timestamp' column
            if "timestamp" in existing_cols and "punch_time" not in existing_cols:
                conn.execute("""
                    UPDATE attendance_log
                    SET punch_time = datetime(timestamp, 'unixepoch', 'localtime')
                    WHERE punch_time IS NULL AND timestamp IS NOT NULL
                """)
                logger.info("Migration: backfilled punch_time from legacy timestamp.")

            # Copy legacy 'synced' → lan_synced + mqtt_synced
            if "synced" in existing_cols:
                conn.execute("""
                    UPDATE attendance_log
                    SET lan_synced  = synced,
                        mqtt_synced = synced
                    WHERE synced = 1
                """)
                logger.info("Migration: copied legacy synced flag to lan_synced/mqtt_synced.")

        logger.info("SQLite database ready at: %s", DB_PATH)

    # ── Shift helpers ─────────────────────────────────────────────────────────

    def get_user_shift(self, user_id=None):
        """Return the first (default) shift. Extend later for per-user shifts."""
        with _get_conn() as conn:
            cur = conn.execute("SELECT * FROM shifts ORDER BY id ASC LIMIT 1")
            row = cur.fetchone()
            return dict(row) if row else None

    # ── Punch helpers ─────────────────────────────────────────────────────────

    def get_last_punch_today(self, user_id):
        today = date.today().isoformat()
        with _get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM attendance_log
                WHERE user_id = ? AND punch_date = ?
                ORDER BY punch_time DESC LIMIT 1
            """, (user_id, today))
            row = cur.fetchone()
            return dict(row) if row else None

    # ── Status calculation ────────────────────────────────────────────────────

    def calculate_attendance_status(self, punch_time: datetime, punch_type: str, shift: dict):
        if not shift:
            return "Present", 0, 0, 0

        status     = "Present"
        late_mins  = 0
        early_mins = 0
        ot_mins    = 0
        base_date  = punch_time.date()

        def to_dt(t_str):
            t = datetime.strptime(t_str, "%H:%M:%S").time()
            return datetime.combine(base_date, t)

        shift_start = to_dt(shift['start_time'])
        shift_end   = to_dt(shift['end_time'])

        if punch_type == 'IN':
            late_threshold = shift_start + timedelta(minutes=int(shift['late_grace_mins']))
            if punch_time > late_threshold:
                diff      = punch_time - shift_start
                late_mins = int(diff.total_seconds() / 60)
                status    = "Half Day" if late_mins > 120 else "Late"

        elif punch_type == 'OUT':
            if punch_time < shift_end:
                diff       = shift_end - punch_time
                early_mins = int(diff.total_seconds() / 60)
                status     = "Half Day (Early)" if early_mins > 60 else "Early Departure"
            elif punch_time > (shift_end + timedelta(minutes=int(shift['overtime_start_mins']))):
                diff    = punch_time - shift_end
                ot_mins = int(diff.total_seconds() / 60)
                status  = "Overtime"

        return status, late_mins, early_mins, ot_mins

    # ── Add record ────────────────────────────────────────────────────────────

    def add_record(self, device_id: str, name: str, user_id: str = None, confidence: float = 0.0):
        dt_now    = datetime.now()
        p_date    = dt_now.date().isoformat()
        p_time    = dt_now.time().strftime("%H:%M:%S")
        user_id   = user_id or name

        # Cooldown: prevent double punches within 60 s
        last_punch = self.get_last_punch_today(user_id)
        if last_punch:
            last_dt = datetime.fromisoformat(last_punch['punch_time'])
            if (dt_now - last_dt).total_seconds() < 60:
                logger.info("Cooldown active for %s — punch ignored.", name)
                return None

        # Auto-toggle IN/OUT
        punch_type = 'IN'
        if last_punch and last_punch['punch_type'] == 'IN':
            punch_type = 'OUT'

        # Shift & status
        shift    = self.get_user_shift(user_id)
        shift_id = shift['id'] if shift else None
        status, late, early, ot = self.calculate_attendance_status(dt_now, punch_type, shift)

        with _get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO attendance_log
                    (user_id, name, device_id, punch_time, punch_date, punch_clock,
                     punch_type, shift_id, attendance_status,
                     late_minutes, early_departure_minutes, overtime_minutes,
                     confidence, lan_synced, mqtt_synced)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,0)
            """, (user_id, name, device_id,
                  dt_now.isoformat(sep=' '), p_date, p_time,
                  punch_type, shift_id, status,
                  late, early, ot, confidence))
            row_id = cur.lastrowid

        logger.info("Saved %s for %s | status=%s late=%dm ot=%dm", punch_type, name, status, late, ot)
        return row_id

    # ── Sync queries — LAN ────────────────────────────────────────────────────

    def get_unsynced_lan_records(self, limit: int = 50):
        with _get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM attendance_log
                WHERE lan_synced = 0
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def mark_lan_synced(self, record_ids: list):
        if not record_ids:
            return
        placeholders = ",".join("?" * len(record_ids))
        with _get_conn() as conn:
            conn.execute(
                f"UPDATE attendance_log SET lan_synced=1 WHERE id IN ({placeholders})",
                record_ids
            )
        logger.info("Marked %d records as lan_synced.", len(record_ids))

    # ── Sync queries — MQTT ───────────────────────────────────────────────────

    def get_unsynced_mqtt_records(self, limit: int = 50):
        with _get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM attendance_log
                WHERE mqtt_synced = 0
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def mark_mqtt_synced(self, record_ids: list):
        if not record_ids:
            return
        placeholders = ",".join("?" * len(record_ids))
        with _get_conn() as conn:
            conn.execute(
                f"UPDATE attendance_log SET mqtt_synced=1 WHERE id IN ({placeholders})",
                record_ids
            )
        logger.info("Marked %d records as mqtt_synced.", len(record_ids))

    # ── Legacy helpers (kept for backward-compat with older code) ─────────────

    def get_unsynced_records(self, limit: int = 50):
        """Alias → returns records not yet LAN-synced."""
        return self.get_unsynced_lan_records(limit)

    def mark_as_synced(self, record_ids: list):
        """Alias → marks both lan_synced and mqtt_synced."""
        self.mark_lan_synced(record_ids)
        self.mark_mqtt_synced(record_ids)

    # ── Employee / Users table ────────────────────────────────────────────────

    def upsert_users(self, user_list: list):
        """
        Insert or update employees from a list of dicts: [{user_id, name}, ...]
        Called by the MQTT subscriber when the dashboard publishes the employee list.
        Uses INSERT OR REPLACE so new entries are added and existing ones are updated.
        """
        if not user_list:
            return
        with _get_conn() as conn:
            for u in user_list:
                uid  = u.get("user_id") or u.get("id")
                name = u.get("name") or u.get("employee_name")
                if uid and name:
                    conn.execute("""
                        INSERT INTO users (user_id, name, synced_at)
                        VALUES (?, ?, datetime('now','localtime'))
                        ON CONFLICT(user_id) DO UPDATE SET
                            name      = excluded.name,
                            synced_at = excluded.synced_at
                    """, (str(uid), str(name)))
        logger.info("Upserted %d users into local users table.", len(user_list))

    def get_all_users(self) -> list:
        """Return all employees from local cache, ordered by name."""
        with _get_conn() as conn:
            cur = conn.execute(
                "SELECT user_id, name FROM users ORDER BY name ASC"
            )
            return [dict(r) for r in cur.fetchall()]
