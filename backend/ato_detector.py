"""
============================================================
NeuralNexus — Stage S6: ATO Chain Detector
============================================================
Detects Account Takeover (ATO) chains in real-time.
Logs session events (login, MFA, profile edits) to an SQLite
database and links them together via a sliding time window.

If a transaction occurs shortly after suspicious session events,
the `ato_chain_active` boolean becomes True, which acts as a
massive multiplier in the ML feature engine.

Usage:
    from ato_detector import ato_detector
    ato_detector.log_event({ ... })
    is_active = ato_detector.detect_ato("usr_123", "sess_xyz")
============================================================
"""

import json
import os
import sqlite3
import time
import uuid
from typing import Optional

# ── Load config ──────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

ATO_WINDOW_SECONDS = int(os.getenv("ATO_WINDOW_SECONDS", "300"))
DB_PATH = os.path.join(os.path.dirname(__file__), "ato_events.db")

class ATODetector:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        # Enable WAL mode for high concurrency (read/write at same time)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Creates tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS session_events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    device_id TEXT,
                    ip_address TEXT,
                    lat REAL,
                    lon REAL,
                    timestamp_utc REAL NOT NULL,
                    metadata_json TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_session_events_user_time 
                ON session_events(user_id, timestamp_utc);
                
                CREATE TABLE IF NOT EXISTS ato_chains (
                    chain_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    risk_score REAL NOT NULL,
                    linked_device TEXT,
                    attacker_ip TEXT
                );
            """)
    def _auto_resolve_chains(self, conn, current_ts: float):
        conn.execute("""
            UPDATE ato_chains 
            SET status = 'resolved', end_time = ?
            WHERE status = 'active' AND start_time < ?
        """, (current_ts, current_ts - ATO_WINDOW_SECONDS))

    def log_event(self, event_data: dict) -> dict:
        """
        Logs a session event.
        Matches the SessionEventRequest from Api Contract.
        """
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        user_id = event_data["user_id"]
        session_id = event_data["session_id"]
        event_type = event_data["event_type"]
        device_id = event_data.get("device_id", "")
        ip_address = event_data.get("ip_address", "")
        lat = float(event_data.get("latitude", 0.0))
        lon = float(event_data.get("longitude", 0.0))
        
        # API sends ISO 8601, but we use internal unix ts
        raw_ts = event_data.get("timestamp_utc")
        if raw_ts is not None:
            try:
                ts = float(raw_ts)
            except ValueError:
                from datetime import datetime
                ts = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00')).timestamp()
        else:
            ts = time.time()
        
        metadata_json = json.dumps(event_data.get("metadata", {}))

        # Check if this event opens a new chain
        high_risk_events = {"login_suspicious", "profile_change", "mfa_fail"}
        is_risky = event_type in high_risk_events
        risk_signal = 80 if is_risky else 10
        chain_id = None
        chain_opened = False

        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, ts)
            conn.execute("""
                INSERT INTO session_events 
                (event_id, user_id, session_id, event_type, device_id, ip_address, lat, lon, timestamp_utc, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, user_id, session_id, event_type, device_id, ip_address, lat, lon, ts, metadata_json))

            if is_risky:
                # Check directly in the same transaction
                existing = conn.execute(
                    "SELECT chain_id FROM ato_chains WHERE user_id=? AND status='active'",
                    (user_id,)
                ).fetchone()
                
                if not existing:
                    chain_id = f"ATO-{uuid.uuid4().hex[:8].upper()}"
                    conn.execute("""
                        INSERT INTO ato_chains 
                        (chain_id, user_id, status, start_time, risk_score, linked_device, attacker_ip)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (chain_id, user_id, "active", ts, risk_signal, device_id, ip_address))
                    chain_opened = True
                else:
                    chain_id = existing[0]
                    chain_opened = False

        return {
            "event_id": event_id,
            "ato_chain_opened": chain_opened,
            "ato_chain_id": chain_id,
            "risk_signal": risk_signal,
            "message": "Event logged"
        }

    def detect_ato(self, user_id: str, session_id: str, now_ts: Optional[float] = None) -> bool:
        """
        Fast lookup: Is there an active chain for this user?
        """
        ts = now_ts or time.time()
        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, ts)
            cursor = conn.execute(
                "SELECT 1 FROM ato_chains WHERE user_id=? AND status='active'", (user_id,)
            )
            return cursor.fetchone() is not None

    def get_ato_features(self, user_id: str, session_id: str) -> dict:
        """Returns all 7 ATO feature values for the ML feature vector."""
        ts = time.time()

        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, ts)
            chain = conn.execute(
                "SELECT risk_score, start_time FROM ato_chains WHERE user_id=? AND status='active'",
                (user_id,)
            ).fetchone()
            
            if not chain:
                return {
                    "ato_chain_active": 0,
                    "ato_chain_risk_score": 0.0,
                    "seconds_since_suspicious_login": 9999.0,
                    "login_new_device": 0,
                    "login_new_ip": 0,
                    "login_mfa_failed": 0,
                    "login_profile_changed": 0,
                }
                
            cutoff = ts - ATO_WINDOW_SECONDS
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT event_type, device_id, ip_address, metadata_json, timestamp_utc
                FROM session_events
                WHERE user_id = ? AND timestamp_utc >= ?
                AND event_type IN ('login_suspicious','mfa_fail','profile_change')
                ORDER BY timestamp_utc DESC LIMIT 1
            """, (user_id, cutoff)).fetchone()

        if not row:
            # Fallback
            return {
                "ato_chain_active": 1,
                "ato_chain_risk_score": float(chain[0]),
                "seconds_since_suspicious_login": round(ts - float(chain[1]), 1),
                "login_new_device": 0,
                "login_new_ip": 0,
                "login_mfa_failed": 0,
                "login_profile_changed": 0,
            }

        meta = json.loads(row["metadata_json"] or "{}")
        return {
            "ato_chain_active": 1,
            "ato_chain_risk_score": 80.0 if row["event_type"] == "login_suspicious" else 60.0,
            "seconds_since_suspicious_login": round(ts - row["timestamp_utc"], 1),
            "login_new_device": int(meta.get("new_device", False)),
            "login_new_ip": int(meta.get("new_ip", False)),
            "login_mfa_failed": int(row["event_type"] == "mfa_fail"),
            "login_profile_changed": int(row["event_type"] == "profile_change"),
        }

    def get_active_chains(self) -> list:
        """Returns all open ATO chains for the dashboard."""
        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, time.time())
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM ato_chains 
                WHERE status = 'active'
                ORDER BY start_time DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
            
    def resolve_chain(self, chain_id: str) -> bool:
        """Marks a chain as resolved (e.g. by an analyst)."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE ato_chains 
                SET status = 'resolved', end_time = ?
                WHERE chain_id = ?
            """, (time.time(), chain_id))
            return cursor.rowcount > 0
            
    def clear_db(self):
        """For testing only."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM session_events")
            conn.execute("DELETE FROM ato_chains")

ato_detector = ATODetector()

# ─────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n[S6] ATO Chain Detector Self-Test")
    print(f"     Window size: {ATO_WINDOW_SECONDS}s")
    
    ato_detector.clear_db()
    
    uid = "usr_tester_99"
    sid = "sess_123"
    
    # 1. Clean login -> detect_ato should be False
    ato_detector.log_event({
        "user_id": uid, "session_id": sid, "event_type": "login_ok",
        "device_id": "dev_1", "ip_address": "1.1.1.1", "metadata": {}
    })
    
    is_ato = ato_detector.detect_ato(uid, sid)
    assert not is_ato, "Clean login should not trigger ATO chain"
    print("     ✓ Clean login ignored")
    
    # 2. Suspicious login -> detect_ato should be True immediately
    res = ato_detector.log_event({
        "user_id": uid, "session_id": sid, "event_type": "login_suspicious",
        "device_id": "dev_2", "ip_address": "2.2.2.2", "metadata": {"reason": "new_device"}
    })
    assert res["ato_chain_opened"], "Suspicious login should open ATO chain"
    
    is_ato = ato_detector.detect_ato(uid, sid)
    assert is_ato, "Suspicious login DO trigger ATO chain"
    print("     ✓ Suspicious login trapped")
    
    # 3. Time travel: past the cutoff window
    # Test that chains close themselves after ATO_WINDOW_SECONDS
    is_ato_past = ato_detector.detect_ato(uid, sid, now_ts=time.time() + ATO_WINDOW_SECONDS + 10)
    assert not is_ato_past, "Chain should close after window expires"
    print("     ✓ Chain expiry window correct")
    
    # 4. Open chains query
    chains = ato_detector.get_active_chains()
    assert len(chains) == 1, "Should have 1 active chain"
    print(f"     ✓ Active chains query works (Active: {chains[0]['chain_id']})")
    
    print("\n✅  S6 Self-Test PASSED.\n")
