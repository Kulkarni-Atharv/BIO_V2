"""
server/api.py
──────────────
LAN Receiver — FastAPI app that runs on any PC/laptop.
The Raspberry Pi POSTs attendance records here over the local network.
Records are stored in data/server_attendance.db (SQLite).

Start with:  python -m uvicorn server.api:app --host 0.0.0.0 --port 8000
Or double-click: server/start_server.bat
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from server.database import ServerDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LAN_API")

app = FastAPI(title="BIO_V2 — LAN Attendance Receiver", version="2.0")
db  = ServerDatabase()


# ─── Data model (matches device/uploader.py payload) ─────────────────────────

class AttendanceRecord(BaseModel):
    device_id:               str
    user_id:                 Optional[str] = None
    name:                    Optional[str] = None
    punch_time:              Optional[str] = None
    punch_date:              Optional[str] = None
    punch_clock:             Optional[str] = None
    punch_type:              Optional[str] = None
    attendance_status:       Optional[str] = None
    late_minutes:            Optional[int] = 0
    early_departure_minutes: Optional[int] = 0
    overtime_minutes:        Optional[int] = 0
    confidence:              Optional[float] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/api/attendance")
async def receive_attendance(records: List[AttendanceRecord]):
    saved = 0
    for rec in records:
        ok = db.insert_attendance(rec.dict())
        if ok:
            saved += 1
        else:
            logger.error("Failed to save record for user %s", rec.user_id)

    logger.info("Received %d records, saved %d.", len(records), saved)
    return {"status": "success", "received": len(records), "saved": saved}


@app.get("/api/attendance")
def get_all_records():
    """View all received records (for debugging / quick dashboard)."""
    return db.get_all_records()


@app.get("/health")
def health_check():
    return {"status": "online", "service": "BIO_V2 LAN Receiver"}


# ─── Standalone run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("server.api:app", host="0.0.0.0", port=8000, reload=False)
