"""
modules/sms_fallback.py
RoadSoS - Low-Network SMS Fallback Engine

Purpose:
  - Queue SOS messages when data network is unavailable
  - Send via SMS (no data required) using device modem APIs
  - Auto-dispatch queued messages when connectivity is restored
  - Integrates with Android/iOS SMS APIs via Flutter bridge (production)

In hackathon demo mode: messages are queued locally and printed.
In production: integrate with Android SmsManager or iOS MessageUI via Flutter.
"""

import json
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional


class SMSFallbackEngine:
    """
    Manages offline SMS queue for emergency distress signals.
    When network unavailable, messages are stored locally and sent when signal returns.
    """

    def __init__(self, queue_db_path: str = "data/sms_queue.db"):
        self.queue_db_path = queue_db_path
        self._init_queue_db()

    def _init_queue_db(self):
        """Initialize local SMS queue database."""
        os.makedirs(os.path.dirname(self.queue_db_path), exist_ok=True)
        conn = sqlite3.connect(self.queue_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sms_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                phone       TEXT NOT NULL,
                message     TEXT NOT NULL,
                queued_at   TEXT DEFAULT (datetime('now')),
                sent        INTEGER DEFAULT 0,
                sent_at     TEXT,
                attempts    INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def queue_sms(self, phone: str, message: str) -> int:
        """Add an SOS SMS to the offline queue."""
        conn = sqlite3.connect(self.queue_db_path)
        cursor = conn.execute(
            "INSERT INTO sms_queue (phone, message) VALUES (?, ?)", (phone, message)
        )
        conn.commit()
        queue_id = cursor.lastrowid
        conn.close()
        print(f"[SMS] Message queued (ID: {queue_id}) to {phone}")
        return queue_id

    def flush_queue(self) -> int:
        """
        Attempt to send all queued messages.
        In production: call Android SmsManager or iOS MessageUI via Flutter/Kotlin bridge.
        Returns number of messages sent.
        """
        conn = sqlite3.connect(self.queue_db_path)
        pending = conn.execute(
            "SELECT * FROM sms_queue WHERE sent = 0 ORDER BY queued_at"
        ).fetchall()

        sent_count = 0
        for row in pending:
            success = self._send_sms(row[1], row[2])  # phone, message
            if success:
                conn.execute(
                    "UPDATE sms_queue SET sent = 1, sent_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), row[0])
                )
                sent_count += 1
            else:
                conn.execute(
                    "UPDATE sms_queue SET attempts = attempts + 1 WHERE id = ?", (row[0],)
                )

        conn.commit()
        conn.close()
        return sent_count

    def _send_sms(self, phone: str, message: str) -> bool:
        """
        Send a single SMS message.
        Production implementation calls the device's native SMS API.
        Demo mode: prints to console and returns True.

        Flutter/Android integration (production):
            MethodChannel('roadsos/sms').invokeMethod('sendSMS', {
                'phone': phone, 'message': message
            })
        """
        # Demo mode: simulate send
        print(f"[SMS SEND] To: {phone}")
        print(f"[SMS SEND] Message: {message[:160]}")
        return True

    def get_queue_status(self) -> Dict:
        conn = sqlite3.connect(self.queue_db_path)
        total = conn.execute("SELECT COUNT(*) FROM sms_queue").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM sms_queue WHERE sent = 0").fetchone()[0]
        sent = total - pending
        conn.close()
        return {"total": total, "pending": pending, "sent": sent}
