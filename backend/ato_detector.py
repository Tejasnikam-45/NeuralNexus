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

Fixes applied vs original:
  Bug 1 — log_event() now correctly reads timestamp_utc from
           event_data instead of always using time.time().
  Bug 2 — session_id is now used in detect_ato() SQL filter
           so cross-session false positives are eliminated.
  Bug 3 — duplicate chain creation is prevented by checking
           for an existing active chain inside the same
           transaction before inserting a new one.
  Bug 4 — get_ato_features() is fully implemented and returns
           all 7 ATO feature values that S8 requires.
  Bug 5 — resolve_chain() exists and is called correctly;
           _auto_resolve_chains() provides expiry audit trail.

Usage:
    from ato_detector import ato_detector
    ato_detector.log_event({ ... })
    features = ato_detector.get_ato_features("usr_123", "sess_xyz")
    is_active = ato_detector.detect_ato("usr_123", "sess_xyz")
============================================================
"""

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
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
        # WAL mode: concurrent reads don't block writes
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Creates tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS session_events (
                    event_id       TEXT PRIMARY KEY,
                    user_id        TEXT NOT NULL,
                    session_id     TEXT NOT NULL,
                    event_type     TEXT NOT NULL,
                    device_id      TEXT,
                    ip_address     TEXT,
                    lat            REAL,
                    lon            REAL,
                    timestamp_utc  REAL NOT NULL,
                    metadata_json  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_session_events_user_time
                ON session_events(user_id, timestamp_utc);

                CREATE TABLE IF NOT EXISTS ato_chains (
                    chain_id      TEXT PRIMARY KEY,
                    user_id       TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    start_time    REAL NOT NULL,
                    end_time      REAL,
                    risk_score    REAL NOT NULL,
                    linked_device TEXT,
                    attacker_ip   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_ato_chains_user_status
                ON ato_chains(user_id, status);
            """)

    # ── Internal helpers ─────────────────────────────────────────

    def _auto_resolve_chains(self, conn, current_ts: float):
        """
        Marks any active chain older than ATO_WINDOW_SECONDS as resolved.
        Called at the top of every read/write operation so the DB stays clean.
        """
        conn.execute("""
            UPDATE ato_chains
            SET status = 'resolved', end_time = ?
            WHERE status = 'active' AND start_time < ?
        """, (current_ts, current_ts - ATO_WINDOW_SECONDS))

    @staticmethod
    def _parse_timestamp(raw_ts) -> float:
        """
        Converts whatever timestamp format the API sends into a float unix ts.
        Accepts: float, int, ISO-8601 string, or None (falls back to now).

        FIX Bug 1: previously log_event() always used time.time() and ignored
        the passed timestamp entirely — breaking the simulator's backdated
        replay scenarios and the chain window logic.
        """
        if raw_ts is None:
            return time.time()
        try:
            return float(raw_ts)
        except (ValueError, TypeError):
            try:
                return datetime.fromisoformat(
                    str(raw_ts).replace("Z", "+00:00")
                ).timestamp()
            except Exception:
                return time.time()

    # ── Public: LOG EVENT ────────────────────────────────────────

    def log_event(self, event_data: dict) -> dict:
        """
        Logs a session event and (if high-risk) opens an ATO chain.

        FIX Bug 1: timestamp is now read from event_data, not time.time().
        FIX Bug 3: duplicate chain creation prevented — only one active
                   chain per user at a time.

        Returns a dict describing what happened (used by /event endpoint).
        """
        event_id   = f"evt_{uuid.uuid4().hex[:12]}"
        user_id    = event_data["user_id"]
        session_id = event_data["session_id"]
        event_type = event_data["event_type"]
        device_id  = event_data.get("device_id", "")
        ip_address = event_data.get("ip_address", "")
        lat        = float(event_data.get("latitude",  0.0))
        lon        = float(event_data.get("longitude", 0.0))

        # FIX Bug 1: use provided timestamp, not time.time()
        ts = self._parse_timestamp(event_data.get("timestamp_utc"))

        metadata_json = json.dumps(event_data.get("metadata", {}))

        high_risk_events = {"login_suspicious", "profile_change", "mfa_fail"}
        is_risky    = event_type in high_risk_events
        risk_signal = 80 if is_risky else 10
        chain_id    = None
        chain_opened = False

        with self._get_conn() as conn:
            # Expire stale chains before any logic runs
            self._auto_resolve_chains(conn, ts)

            # Insert the session event
            conn.execute("""
                INSERT INTO session_events
                (event_id, user_id, session_id, event_type, device_id,
                 ip_address, lat, lon, timestamp_utc, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, user_id, session_id, event_type, device_id,
                  ip_address, lat, lon, ts, metadata_json))

            # FIX Bug 3: check for existing active chain INSIDE the same
            # transaction so concurrent calls cannot both pass the check.
            if is_risky:
                existing = conn.execute(
                    "SELECT chain_id FROM ato_chains "
                    "WHERE user_id = ? AND status = 'active'",
                    (user_id,)
                ).fetchone()

                if not existing:
                    chain_id = f"ATO-{uuid.uuid4().hex[:8].upper()}"
                    conn.execute("""
                        INSERT INTO ato_chains
                        (chain_id, user_id, status, start_time, risk_score,
                         linked_device, attacker_ip)
                        VALUES (?, ?, 'active', ?, ?, ?, ?)
                    """, (chain_id, user_id, ts, risk_signal, device_id, ip_address))
                    chain_opened = True
                else:
                    chain_id     = existing[0]
                    chain_opened = False

        return {
            "event_id":        event_id,
            "ato_chain_opened": chain_opened,
            "ato_chain_id":    chain_id,
            "risk_signal":     risk_signal,
            "message":         "Event logged",
        }

    # ── Public: DETECT ATO (fast bool) ──────────────────────────

    def detect_ato(
        self,
        user_id:    str,
        session_id: str,
        now_ts:     Optional[float] = None,
    ) -> bool:
        """
        Fast lookup: Is there an active ATO chain for this user?

        FIX Bug 2: session_id is now included in the query so a suspicious
        login from session A cannot false-positive a completely different
        session B for the same user.

        Note: we still keep a user_id-level fallback because ATO chains are
        created at the user level (the attacker controls the account, not
        just one session). The session_id check uses OR so that either
        condition matches — user-level chain OR matching session.
        This preserves cross-session ATO detection while eliminating
        pure stale-session false positives.
        """
        ts = now_ts or time.time()
        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, ts)
            # FIX Bug 2: filter by session_id OR a chain started by this session
            cursor = conn.execute("""
                SELECT 1 FROM ato_chains ac
                WHERE ac.user_id = ? AND ac.status = 'active'
                AND (
                    ac.linked_device IN (
                        SELECT device_id FROM session_events
                        WHERE session_id = ? AND user_id = ?
                    )
                    OR ac.attacker_ip IN (
                        SELECT ip_address FROM session_events
                        WHERE session_id = ? AND user_id = ?
                    )
                    OR EXISTS (
                        SELECT 1 FROM session_events se
                        WHERE se.session_id = ? AND se.user_id = ?
                        AND se.event_type IN ('login_suspicious','mfa_fail','profile_change')
                    )
                )
                LIMIT 1
            """, (user_id, session_id, user_id, session_id, user_id, session_id, user_id))
            return cursor.fetchone() is not None

    # ── Public: GET ATO FEATURES (called by S8 per transaction) ─

    def get_ato_features(self, user_id: str, session_id: str) -> dict:
        """
        Returns the 7 ATO feature values the ML scoring engine (S8) needs
        to build the 46-feature inference vector.

        FIX Bug 4: this method was completely absent in the original code,
        causing a KeyError on the very first scoring request in S8.

        FIX (row_factory): conn.row_factory = sqlite3.Row is now set BEFORE
        any query runs so both the chain query and row query use named column
        access. Previously it was set mid-connection which is unreliable on
        Windows SQLite3 drivers.

        Feature contract (matches feature_schema.py ATO_FEATURES):
            ato_chain_active              int   0 or 1
            ato_chain_risk_score          float 0–100
            seconds_since_suspicious_login float large if no chain
            login_new_device              int   0 or 1
            login_new_ip                  int   0 or 1
            login_mfa_failed              int   0 or 1
            login_profile_changed         int   0 or 1
        """
        ts     = time.time()
        cutoff = ts - ATO_WINDOW_SECONDS

        # Open connection with row_factory set BEFORE any query.
        # isolation_level=None = autocommit: guarantees we read all WAL-committed
        # data written by log_event() on other connections.
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            self._auto_resolve_chains(conn, ts)

            chain = conn.execute(
                "SELECT risk_score, start_time FROM ato_chains "
                "WHERE user_id = ? AND status = 'active' "
                "ORDER BY start_time DESC LIMIT 1",
                (user_id,)
            ).fetchone()

            if not chain:
                return {
                    "ato_chain_active":               0,
                    "ato_chain_risk_score":           0.0,
                    "seconds_since_suspicious_login": 9999.0,
                    "login_new_device":               0,
                    "login_new_ip":                   0,
                    "login_mfa_failed":               0,
                    "login_profile_changed":          0,
                }

            # Chain exists — look up the originating suspicious login event
            # by matching the chain's linked_device or attacker_ip.
            # This avoids picking a later mfa_fail (which has empty metadata).
            row = conn.execute("""
                SELECT se.event_type, se.device_id, se.ip_address,
                       se.metadata_json, se.timestamp_utc
                FROM session_events se
                INNER JOIN ato_chains ac
                    ON ac.user_id = se.user_id
                    AND (se.device_id = ac.linked_device OR se.ip_address = ac.attacker_ip)
                WHERE se.user_id = ? AND se.timestamp_utc >= ?
                AND se.event_type IN ('login_suspicious', 'mfa_fail', 'profile_change')
                ORDER BY se.timestamp_utc ASC LIMIT 1
            """, (user_id, cutoff)).fetchone()

        finally:
            conn.close()

        if not row:
            # Chain exists but no matching event row (edge case: DB partially written)
            return {
                "ato_chain_active":               1,
                "ato_chain_risk_score":           float(chain["risk_score"]),
                "seconds_since_suspicious_login": round(ts - float(chain["start_time"]), 1),
                "login_new_device":               0,
                "login_new_ip":                   0,
                "login_mfa_failed":               0,
                "login_profile_changed":          0,
            }

        meta = json.loads(row["metadata_json"] or "{}")
        return {
            "ato_chain_active":               1,
            "ato_chain_risk_score":           80.0 if row["event_type"] == "login_suspicious" else 60.0,
            "seconds_since_suspicious_login": round(ts - row["timestamp_utc"], 1),
            "login_new_device":               int(meta.get("new_device", False)),
            "login_new_ip":                   int(meta.get("new_ip", False)),
            "login_mfa_failed":               int(row["event_type"] == "mfa_fail"),
            "login_profile_changed":          int(row["event_type"] == "profile_change"),
        }

    # ── Public: GET ACTIVE CHAINS (dashboard) ───────────────────

    def get_active_chains(self) -> list:
        """Returns all open ATO chains for the analyst dashboard."""
        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, time.time())
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM ato_chains
                WHERE status = 'active'
                ORDER BY start_time DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    # ── Public: RESOLVE CHAIN (analyst action / FIX Bug 5) ──────

    def resolve_chain(self, chain_id: str) -> bool:
        """
        Marks a chain as resolved.
        Called by the POST /feedback endpoint when an analyst confirms
        a false positive, or by the adaptive retraining loop.

        FIX Bug 5: chains now have a proper resolution path instead of
        silently falling off the dashboard when the window expires.
        """
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE ato_chains
                SET status = 'resolved', end_time = ?
                WHERE chain_id = ?
            """, (time.time(), chain_id))
            return cursor.rowcount > 0

    # ── Public: GET CHAIN HISTORY (for /users/{id} panel) ───────

    def get_chain_history(self, user_id: str, limit: int = 20) -> list:
        """
        Returns resolved + active chains for a user.
        Used by the analyst detail panel to show the full ATO timeline.
        """
        with self._get_conn() as conn:
            self._auto_resolve_chains(conn, time.time())
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM ato_chains
                WHERE user_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # ── Public: CLEAR DB (tests only) ───────────────────────────

    def clear_db(self):
        """Wipes all data. Used by self-test only — never call in production."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM session_events")
            conn.execute("DELETE FROM ato_chains")


# Module-level singleton — imported by FastAPI as:
#   from ato_detector import ato_detector
ato_detector = ATODetector()


# ─────────────────────────────────────────────────────────────
# SELF-TEST
# Run: python backend/ato_detector.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n[S6] ATO Chain Detector Self-Test")
    print(f"     Window size: {ATO_WINDOW_SECONDS}s")

    ato_detector.clear_db()

    uid  = "usr_tester_99"
    sid  = "sess_123"
    now  = time.time()

    # ── Test 1: Clean login should not open a chain ──────────────
    ato_detector.log_event({
        "user_id": uid, "session_id": sid, "event_type": "login_ok",
        "device_id": "dev_1", "ip_address": "1.1.1.1",
        "timestamp_utc": now, "metadata": {},
    })
    assert not ato_detector.detect_ato(uid, sid), \
        "Clean login must not trigger ATO chain"
    print("     ✓ Clean login ignored")

    # ── Test 2: Suspicious login should open a chain ─────────────
    res = ato_detector.log_event({
        "user_id": uid, "session_id": sid, "event_type": "login_suspicious",
        "device_id": "dev_2", "ip_address": "2.2.2.2",
        "timestamp_utc": now + 1,
        "metadata": {"new_device": True, "new_ip": True, "reason": "geo_anomaly"},
    })
    assert res["ato_chain_opened"], "Suspicious login must open ATO chain"
    chain_id = res["ato_chain_id"]

    assert ato_detector.detect_ato(uid, sid), \
        "detect_ato must return True after suspicious login"
    print(f"     ✓ Suspicious login trapped  (chain={chain_id})")

    # ── Test 3: Duplicate suppression — second suspicious event   ─
    #            should NOT open a second chain
    res2 = ato_detector.log_event({
        "user_id": uid, "session_id": sid, "event_type": "mfa_fail",
        "device_id": "dev_2", "ip_address": "2.2.2.2",
        "timestamp_utc": now + 5, "metadata": {},
    })
    assert not res2["ato_chain_opened"], \
        "Second suspicious event must NOT open a new chain"
    assert res2["ato_chain_id"] == chain_id, \
        "Second event must reuse the existing chain_id"
    print("     ✓ Duplicate chain suppressed correctly")

    # ── Test 4: get_ato_features returns all 7 keys ──────────────
    features = ato_detector.get_ato_features(uid, sid)
    required_keys = {
        "ato_chain_active", "ato_chain_risk_score",
        "seconds_since_suspicious_login",
        "login_new_device", "login_new_ip",
        "login_mfa_failed", "login_profile_changed",
    }
    assert required_keys == set(features.keys()), \
        f"Feature keys mismatch: {set(features.keys())}"
    assert features["ato_chain_active"] == 1
    assert features["login_new_device"] == 1
    assert features["login_new_ip"] == 1
    assert features["seconds_since_suspicious_login"] < ATO_WINDOW_SECONDS
    print(f"     ✓ get_ato_features OK: {features}")

    # ── Test 5: Chain expires after window ───────────────────────
    future_ts = now + ATO_WINDOW_SECONDS + 10
    assert not ato_detector.detect_ato(uid, sid, now_ts=future_ts), \
        "Chain must auto-expire after ATO_WINDOW_SECONDS"
    print("     ✓ Chain expiry window correct")

    # ── Test 6: No-chain baseline for get_ato_features ───────────
    ato_detector.clear_db()
    feats_clean = ato_detector.get_ato_features("usr_no_chain", "sess_abc")
    assert feats_clean["ato_chain_active"] == 0
    assert feats_clean["ato_chain_risk_score"] == 0.0
    assert feats_clean["seconds_since_suspicious_login"] == 9999.0
    print("     ✓ Clean user returns zero ATO features")

    # ── Test 7: resolve_chain works ──────────────────────────────
    ato_detector.clear_db()
    res3 = ato_detector.log_event({
        "user_id": "usr_resolve_test", "session_id": "sess_r",
        "event_type": "login_suspicious", "device_id": "dev_x",
        "ip_address": "3.3.3.3", "timestamp_utc": time.time(), "metadata": {},
    })
    resolved = ato_detector.resolve_chain(res3["ato_chain_id"])
    assert resolved, "resolve_chain must return True on success"
    chains = ato_detector.get_active_chains()
    assert all(c["chain_id"] != res3["ato_chain_id"] for c in chains), \
        "Resolved chain must not appear in get_active_chains()"
    print("     ✓ resolve_chain works correctly")

    # ── Test 8: Backdated timestamp (FIX Bug 1 verification) ─────
    ato_detector.clear_db()
    backdated_ts = time.time() - 200   # 200s ago, within 300s window
    ato_detector.log_event({
        "user_id": "usr_backdate", "session_id": "sess_bd",
        "event_type": "login_suspicious", "device_id": "dev_bd",
        "ip_address": "4.4.4.4", "timestamp_utc": backdated_ts, "metadata": {},
    })
    # Chain should still be active (200s < 300s window)
    assert ato_detector.detect_ato("usr_backdate", "sess_bd"), \
        "Backdated event within window must still be active"
    # Chain should be expired if we check 110s later (200+110 > 300)
    assert not ato_detector.detect_ato(
        "usr_backdate", "sess_bd", now_ts=time.time() + 110
    ), "Backdated event must expire correctly based on its own timestamp"
    print("     ✓ Backdated timestamp handling correct (Bug 1 fix verified)")

    print("\n✅  S6 Self-Test PASSED — ATO Detector ready for S8 (FastAPI)\n")