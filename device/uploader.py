"""
device/uploader.py
──────────────────
LAN Sync Service — runs as a background thread inside hmi.py (or standalone).

Behaviour
  • Every `interval` seconds, checks if the LAN receiver PC is reachable
    (fast TCP probe on LAN_SERVER_IP:LAN_SERVER_PORT).
  • If reachable  → POST unsynced records, mark lan_synced = 1.
  • If unreachable → skip silently, retry next cycle. No crash, no noise.
"""

import threading
import time
import socket
import requests
import json
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config import API_BASE_URL, DEVICE_ID, LAN_SERVER_IP, LAN_SERVER_PORT
from device.database import LocalDatabase

logger = logging.getLogger("LAN_Uploader")


def _is_lan_reachable(host: str, port: int, timeout: float = 1.5) -> bool:
    """TCP probe — returns True if the server socket is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class DataUploader:
    def __init__(self, db: LocalDatabase, interval: int = 10):
        self.db       = db
        self.interval = interval
        self.running  = False
        self.thread   = None

    def start(self):
        self.running = True
        self.thread  = threading.Thread(target=self._run_loop, daemon=True, name="LAN-Uploader")
        self.thread.start()
        logger.info("LAN Uploader started (target: %s:%s)", LAN_SERVER_IP, LAN_SERVER_PORT)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("LAN Uploader stopped.")

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run_loop(self):
        while self.running:
            try:
                if _is_lan_reachable(LAN_SERVER_IP, LAN_SERVER_PORT):
                    self._sync_data()
                else:
                    logger.debug("LAN PC not reachable — will retry in %ds.", self.interval)
            except Exception as e:
                logger.error("Uploader error: %s", e)
            time.sleep(self.interval)

    def _sync_data(self):
        records = self.db.get_unsynced_lan_records(limit=50)
        if not records:
            return

        # Build JSON-serialisable payload
        payload    = []
        record_ids = []
        for r in records:
            payload.append({
                "device_id":               r["device_id"],
                "user_id":                 r["user_id"],
                "name":                    r["name"],
                "punch_time":              r["punch_time"],
                "punch_date":              r["punch_date"],
                "punch_clock":             r["punch_clock"],
                "punch_type":              r["punch_type"],
                "attendance_status":       r["attendance_status"],
                "late_minutes":            r["late_minutes"],
                "early_departure_minutes": r["early_departure_minutes"],
                "overtime_minutes":        r["overtime_minutes"],
                "confidence":              r["confidence"],
            })
            record_ids.append(r["id"])

        try:
            resp = requests.post(
                f"{API_BASE_URL}/attendance",
                json=payload,
                timeout=8
            )
            if resp.status_code == 200:
                self.db.mark_lan_synced(record_ids)
                logger.info("LAN sync: %d records sent.", len(record_ids))
            else:
                logger.warning("LAN server returned %s — will retry.", resp.status_code)
        except requests.exceptions.RequestException as e:
            logger.warning("LAN POST failed: %s — will retry.", e)
