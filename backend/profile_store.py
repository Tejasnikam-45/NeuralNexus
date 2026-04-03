"""
============================================================
NeuralNexus — Stage S4: Behavioral Profile Store
============================================================
Per-user rolling behavioural statistics stored in Redis.
Used at INFERENCE TIME (Stage S8) to compute profile features
that feed the ML ensemble (Stage S5).

Architecture
────────────
  FastAPI POST /score
      │
      ▼
  profile_store.get_profile(user_id)   ← this file
      │  returns ProfileSnapshot
      ▼
  feature_engineering → ML ensemble → risk score
      │
      ▼
  profile_store.update_profile(user_id, txn)  ← called AFTER decision

Fixes applied vs original:
  Bug 1 — update_profile() now initialises first_txn_ts as
           now - 30*86400 for new users, matching the cold-start
           value in get_profile(). Previously it used `now`,
           making account_age_days permanently 0 after the first
           transaction.
  Bug 2 — velocity sorted-set keys now include a uuid4 suffix so
           two transactions at the same unix timestamp don't
           silently overwrite each other in the sorted set.

Key design decisions
────────────────────
  • Redis hash per user  →  key  "profile:{user_id}"
  • Welford online algorithm → rolling mean + std without storing history
  • TTL = 90 days  →  dormant users auto-expire (no manual cleanup)
  • fakeredis  →  zero-setup for demo mode (USE_REAL_REDIS=0 in .env)
  • Cold-start  →  new users get global PaySim medians, not zero
    (zero would make amount_to_user_mean_ratio = infinity → model breaks)
  • All velocity windows (1h / 24h / 7d) stored as sorted-set timestamps
    → O(log N) insert, O(log N) range query — stays under 5ms budget

Feature mapping to feature_schema.py
──────────────────────────────────────
  PROFILE SOURCE features this module provides:
    is_new_device            ← not in profile.known_devices
    is_new_ip                ← not in profile.known_ips
    device_count_seen        ← len(profile.known_devices)
    txn_count_last_1h        ← sorted-set count in last 3600s
    txn_count_last_24h       ← sorted-set count in last 86400s
    txn_count_last_7d        ← sorted-set count in last 604800s
    inter_txn_seconds        ← now - profile.last_txn_ts
    account_age_days         ← (now - profile.first_txn_ts) / 86400
    mean_txn_amount          ← Welford mean
    std_txn_amount           ← Welford std
    txn_count_total          ← Welford n

Usage
─────
  from profile_store import store, ProfileSnapshot
  snap = store.get_profile(user_id, device_id, ip, now_ts)
  # ... build feature vector ...
  store.update_profile(user_id, device_id, ip, amount, now_ts)

Run self-test:
    python backend/profile_store.py
============================================================
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional

# ── dotenv support ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Redis client ───────────────────────────────────────────────
USE_REAL_REDIS = os.getenv("USE_REAL_REDIS", "0") == "1"

if USE_REAL_REDIS:
    import redis
    _redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
else:
    try:
        import fakeredis
        _redis_client = fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        raise ImportError(
            "fakeredis not installed. Run: pip install fakeredis\n"
            "Or set USE_REAL_REDIS=1 and start a real Redis server."
        )

# ─────────────────────────────────────────────
# GLOBAL COLD-START DEFAULTS
# Derived from data/processed/dataset_stats.json
# so new-user features are realistic, not zero.
# ─────────────────────────────────────────────

_GLOBAL_MEAN_AMOUNT   = 179_861.89
_GLOBAL_STD_AMOUNT    = 603_858.25
_GLOBAL_MEDIAN_AMOUNT = 74_871.94

COLD_START_DEFAULTS = {
    "welford_n":    1,
    "welford_mean": _GLOBAL_MEDIAN_AMOUNT,
    "welford_M2":   _GLOBAL_STD_AMOUNT ** 2,
    "first_txn_ts": None,   # filled at access time → now - 30*86400
    "last_txn_ts":  None,   # filled at access time → now - 3600
    "total_txn_count": 0,
}

PROFILE_TTL_SECONDS = 90 * 24 * 3600

VELOCITY_WINDOWS = {
    "1h":  3_600,
    "24h": 86_400,
    "7d":  604_800,
}

_HASH_PREFIX     = "profile:"
_DEVICES_PREFIX  = "devices:"
_IPS_PREFIX      = "ips:"
_VELOCITY_PREFIX = "velocity:"
_GEO_PREFIX      = "geo:"


# ─────────────────────────────────────────────
# PROFILE SNAPSHOT
# ─────────────────────────────────────────────

@dataclass
class ProfileSnapshot:
    """
    Immutable snapshot of a user's profile at a point in time.
    Values are FEATURE-READY — computed, not raw Redis strings.
    """
    user_id:           str
    is_new_user:       bool

    mean_txn_amount:   float
    std_txn_amount:    float
    txn_count_total:   int

    is_new_device:     bool
    is_new_ip:         bool
    device_count_seen: int

    txn_count_last_1h:  int
    txn_count_last_24h: int
    txn_count_last_7d:  int

    inter_txn_seconds:  float
    account_age_days:   float

    last_lat: float
    last_lon: float

    def to_feature_dict(self) -> dict:
        """Returns only the keys that match feature_schema.py PROFILE_FEATURES."""
        return {
            "is_new_device":      int(self.is_new_device),
            "is_new_ip":          int(self.is_new_ip),
            "device_count_seen":  self.device_count_seen,
            "txn_count_last_1h":  self.txn_count_last_1h,
            "txn_count_last_24h": self.txn_count_last_24h,
            "txn_count_last_7d":  self.txn_count_last_7d,
            "inter_txn_seconds":  self.inter_txn_seconds,
            "account_age_days":   self.account_age_days,
            "mean_txn_amount":    self.mean_txn_amount,
            "std_txn_amount":     self.std_txn_amount,
            "txn_count_total":    self.txn_count_total,
        }


# ─────────────────────────────────────────────
# WELFORD HELPERS
# ─────────────────────────────────────────────

def welford_update(n: int, mean: float, M2: float, x: float) -> tuple[int, float, float]:
    """One Welford step. Returns updated (n, mean, M2)."""
    n     += 1
    delta  = x - mean
    mean  += delta / n
    delta2 = x - mean
    M2    += delta * delta2
    return n, mean, M2

def welford_std(n: int, M2: float) -> float:
    """Sample std from Welford accumulators. Returns 0 if n < 2."""
    if n < 2:
        return 0.0
    return math.sqrt(M2 / (n - 1))


# ─────────────────────────────────────────────
# PROFILE STORE
# ─────────────────────────────────────────────

class ProfileStore:
    """
    Redis-backed per-user behavioral profile store.

    All methods are synchronous. FastAPI runs them in a thread-pool
    executor when called from async endpoints — Redis I/O is fast
    enough that they fit comfortably in the <5ms latency budget.
    """

    def __init__(self, client=None):
        self._r = client or _redis_client

    # ── Key helpers ───────────────────────────────────────────────

    def _hash_key(self, uid: str) -> str: return f"{_HASH_PREFIX}{uid}"
    def _dev_key(self,  uid: str) -> str: return f"{_DEVICES_PREFIX}{uid}"
    def _ip_key(self,   uid: str) -> str: return f"{_IPS_PREFIX}{uid}"
    def _vel_key(self,  uid: str) -> str: return f"{_VELOCITY_PREFIX}{uid}"
    def _geo_key(self,  uid: str) -> str: return f"{_GEO_PREFIX}{uid}"

    # ── GET PROFILE ───────────────────────────────────────────────

    def get_profile(
        self,
        user_id:   str,
        device_id: str,
        ip:        str,
        now_ts:    Optional[float] = None,
        lat:       float = 0.0,
        lon:       float = 0.0,
    ) -> ProfileSnapshot:
        """
        Look up user profile and return a ProfileSnapshot ready for
        feature computation.

        Cold-start defaults apply for users with no history.
        """
        now = now_ts or time.time()
        hk  = self._hash_key(user_id)

        raw        = self._r.hgetall(hk)
        is_new_user = len(raw) == 0

        if is_new_user:
            # Synthetic 30-day-old account for cold-start stability
            first_ts = now - 30 * 86_400
            last_ts  = now - 3_600
            wn    = int(COLD_START_DEFAULTS["welford_n"])
            wmean = float(COLD_START_DEFAULTS["welford_mean"])
            wM2   = float(COLD_START_DEFAULTS["welford_M2"])
            total = int(COLD_START_DEFAULTS["total_txn_count"])
        else:
            # FIX Bug 1 (read side): consistently fall back to now-30d
            # so account_age_days is correct even on the very first update.
            first_ts = float(raw.get("first_txn_ts", now - 30 * 86_400))
            last_ts  = float(raw.get("last_txn_ts",  now - 3_600))
            wn    = int(raw.get("welford_n",       1))
            wmean = float(raw.get("welford_mean",  _GLOBAL_MEDIAN_AMOUNT))
            wM2   = float(raw.get("welford_M2",    _GLOBAL_STD_AMOUNT ** 2))
            total = int(raw.get("total_txn_count", 0))

        mean_amt = wmean
        std_amt  = welford_std(wn, wM2)

        dk = self._dev_key(user_id)
        ik = self._ip_key(user_id)

        is_new_device     = not self._r.sismember(dk, device_id)
        is_new_ip         = not self._r.sismember(ik, ip)
        device_count_seen = int(self._r.scard(dk))

        vk      = self._vel_key(user_id)
        txn_1h  = int(self._r.zcount(vk, now - VELOCITY_WINDOWS["1h"],  now))
        txn_24h = int(self._r.zcount(vk, now - VELOCITY_WINDOWS["24h"], now))
        txn_7d  = int(self._r.zcount(vk, now - VELOCITY_WINDOWS["7d"],  now))

        inter_txn_sec = max(1.0, now - last_ts)
        account_age_d = max(0.0, (now - first_ts) / 86_400)

        gk      = self._geo_key(user_id)
        geo_raw = self._r.hgetall(gk)
        last_lat = float(geo_raw.get("lat", lat))
        last_lon = float(geo_raw.get("lon", lon))

        return ProfileSnapshot(
            user_id=user_id,
            is_new_user=is_new_user,
            mean_txn_amount=mean_amt,
            std_txn_amount=std_amt,
            txn_count_total=total,
            is_new_device=is_new_device,
            is_new_ip=is_new_ip,
            device_count_seen=device_count_seen,
            txn_count_last_1h=txn_1h,
            txn_count_last_24h=txn_24h,
            txn_count_last_7d=txn_7d,
            inter_txn_seconds=inter_txn_sec,
            account_age_days=account_age_d,
            last_lat=last_lat,
            last_lon=last_lon,
        )

    # ── UPDATE PROFILE ────────────────────────────────────────────

    def update_profile(
        self,
        user_id:   str,
        device_id: str,
        ip:        str,
        amount:    float,
        now_ts:    Optional[float] = None,
        lat:       float = 0.0,
        lon:       float = 0.0,
    ) -> None:
        """
        Update the user's profile AFTER a transaction has been processed.
        Pipeline-batched into a single Redis round-trip for speed.

        FIX Bug 1: first_txn_ts defaults to now - 30*86400 for new users,
                   matching the cold-start sentinel in get_profile().
                   Previously it used `now`, making account_age_days = 0
                   permanently after the very first transaction.

        FIX Bug 2: velocity sorted-set key now includes a uuid4 suffix so
                   two transactions at the same unix timestamp (common in
                   PaySim replay) don't overwrite each other.
        """
        now = now_ts or time.time()
        hk  = self._hash_key(user_id)

        raw = self._r.hmget(hk, "welford_n", "welford_mean", "welford_M2",
                            "first_txn_ts", "total_txn_count")

        wn    = int(raw[0])   if raw[0] is not None else 0
        wmean = float(raw[1]) if raw[1] is not None else 0.0
        wM2   = float(raw[2]) if raw[2] is not None else 0.0
        total = int(raw[4])   if raw[4] is not None else 0

        # FIX Bug 1: new users get now-30d, not now
        first = float(raw[3]) if raw[3] is not None else (now - 30 * 86_400)

        wn, wmean, wM2 = welford_update(wn, wmean, wM2, amount)

        pipe = self._r.pipeline(transaction=False)

        pipe.hset(hk, mapping={
            "welford_n":       wn,
            "welford_mean":    wmean,
            "welford_M2":      wM2,
            "first_txn_ts":    first,
            "last_txn_ts":     now,
            "total_txn_count": total + 1,
        })
        pipe.expire(hk, PROFILE_TTL_SECONDS)

        dk = self._dev_key(user_id)
        pipe.sadd(dk, device_id)
        pipe.expire(dk, PROFILE_TTL_SECONDS)

        ik = self._ip_key(user_id)
        pipe.sadd(ik, ip)
        pipe.expire(ik, PROFILE_TTL_SECONDS)

        vk = self._vel_key(user_id)
        # FIX Bug 2: add uuid suffix so same-timestamp transactions are
        # stored as separate members instead of silently overwriting.
        vel_key = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe.zadd(vk, {vel_key: now})
        pipe.zremrangebyscore(vk, 0, now - VELOCITY_WINDOWS["7d"])
        pipe.expire(vk, PROFILE_TTL_SECONDS)

        gk = self._geo_key(user_id)
        if lat != 0.0 or lon != 0.0:
            pipe.hset(gk, mapping={"lat": lat, "lon": lon})
            pipe.expire(gk, PROFILE_TTL_SECONDS)

        pipe.execute()

    # ── DELETE (GDPR / testing) ───────────────────────────────────

    def delete_profile(self, user_id: str) -> int:
        keys = [
            self._hash_key(user_id), self._dev_key(user_id),
            self._ip_key(user_id),   self._vel_key(user_id),
            self._geo_key(user_id),
        ]
        return self._r.delete(*keys)

    # ── HEALTH CHECK ─────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            return self._r.ping()
        except Exception:
            return False

    # ── GET PROFILE RAW (for /users/{id} dashboard panel) ────────

    def get_profile_raw(self, user_id: str) -> dict:
        """
        Returns the raw Redis hash for the analyst detail panel.
        S8's GET /users/{id} endpoint uses this to show full account stats.
        """
        return self._r.hgetall(self._hash_key(user_id))

    # ── BULK SEED (demo / pre-warming) ───────────────────────────

    def seed_demo_profiles(self, profiles: list[dict]) -> int:
        """
        Pre-warm the store with demo profiles so the dashboard shows
        realistic per-user data from the very first request.

        Each dict should have:
            user_id, mean_amount, std_amount, txn_count,
            device_ids (list), known_ips (list), account_age_days
        """
        now    = time.time()
        seeded = 0

        for p in profiles:
            uid  = p["user_id"]
            n    = p.get("txn_count", 10)
            mean = p.get("mean_amount", _GLOBAL_MEDIAN_AMOUNT)
            std  = p.get("std_amount",  _GLOBAL_STD_AMOUNT * 0.1)
            M2   = (std ** 2) * (n - 1) if n > 1 else 0.0

            # FIX Bug 1 consistency: seed first_txn_ts using account_age_days
            first_ts = now - p.get("account_age_days", 30) * 86_400

            hk = self._hash_key(uid)
            self._r.hset(hk, mapping={
                "welford_n":       n,
                "welford_mean":    mean,
                "welford_M2":      M2,
                "first_txn_ts":    first_ts,
                "last_txn_ts":     now - 3600,
                "total_txn_count": n,
            })
            self._r.expire(hk, PROFILE_TTL_SECONDS)

            dk = self._dev_key(uid)
            for dev in p.get("device_ids", ["dev_known_1"]):
                self._r.sadd(dk, dev)
            self._r.expire(dk, PROFILE_TTL_SECONDS)

            ik = self._ip_key(uid)
            for ip_addr in p.get("known_ips", ["192.168.1.1"]):
                self._r.sadd(ik, ip_addr)
            self._r.expire(ik, PROFILE_TTL_SECONDS)

            seeded += 1

        return seeded


# ─────────────────────────────────────────────
# DEMO PROFILES (matches mockData.js in the UI)
# ─────────────────────────────────────────────

DEMO_PROFILES = [
    {
        "user_id": "usr_alex92",
        "mean_amount": 380.0, "std_amount": 200.0, "txn_count": 142,
        "device_ids": ["dev_chrome_win_a92"],
        "known_ips": ["203.0.113.10"],
        "account_age_days": 420,
    },
    {
        "user_id": "usr_sarah_k",
        "mean_amount": 220.0, "std_amount": 90.0, "txn_count": 289,
        "device_ids": ["dev_safari_mac_sk"],
        "known_ips": ["198.51.100.22"],
        "account_age_days": 730,
    },
    {
        "user_id": "usr_mike99",
        "mean_amount": 150.0, "std_amount": 110.0, "txn_count": 97,
        "device_ids": ["dev_firefox_linux_m99"],
        "known_ips": ["203.0.113.55"],
        "account_age_days": 180,
    },
    {
        "user_id": "usr_priya_m",
        "mean_amount": 95.0, "std_amount": 40.0, "txn_count": 561,
        "device_ids": ["dev_chrome_android_pm"],
        "known_ips": ["203.0.113.77"],
        "account_age_days": 1100,
    },
    {
        "user_id": "usr_james_w",
        "mean_amount": 410.0, "std_amount": 320.0, "txn_count": 66,
        "device_ids": ["dev_edge_win_jw"],
        "known_ips": ["198.51.100.88"],
        "account_age_days": 95,
    },
    {
        "user_id": "usr_tom_b",
        "mean_amount": 310.0, "std_amount": 250.0, "txn_count": 48,
        "device_ids": ["dev_chrome_ios_tb"],
        "known_ips": ["198.51.100.33"],
        "account_age_days": 55,
    },
]


# ─────────────────────────────────────────────
# MODULE-LEVEL SINGLETON
# ─────────────────────────────────────────────

store = ProfileStore()


# ─────────────────────────────────────────────
# SELF-TEST
# Run: python backend/profile_store.py
# ─────────────────────────────────────────────

def _self_test():
    print("\n[S4] Profile Store Self-Test")
    print(f"     Backend: {'Real Redis' if USE_REAL_REDIS else 'fakeredis'}")

    ps = ProfileStore()

    if not ps.ping():
        print("❌  Redis ping failed — check connection")
        return
    print("     ✓ Redis ping OK")

    # ── Test 1: Cold-start ────────────────────────────────────────
    uid = "test_user_selftest"
    ps.delete_profile(uid)

    snap = ps.get_profile(uid, device_id="dev_A", ip="1.2.3.4")
    assert snap.is_new_user,         "Expected new_user=True on cold start"
    assert snap.is_new_device,       "Expected is_new_device=True on cold start"
    assert snap.is_new_ip,           "Expected is_new_ip=True on cold start"
    assert snap.txn_count_last_1h == 0
    assert snap.mean_txn_amount == _GLOBAL_MEDIAN_AMOUNT
    print("     ✓ Cold-start snapshot correct")

    # ── Test 2: Update then re-read ───────────────────────────────
    now     = time.time()
    amounts = [100.0, 200.0, 150.0, 130.0, 175.0]
    for amt in amounts:
        ps.update_profile(uid, device_id="dev_A", ip="1.2.3.4",
                          amount=amt, now_ts=now)
        now += 60

    snap2 = ps.get_profile(uid, device_id="dev_A", ip="1.2.3.4", now_ts=now)
    assert not snap2.is_new_user
    assert not snap2.is_new_device
    assert not snap2.is_new_ip
    assert snap2.txn_count_total == len(amounts), \
        f"Expected {len(amounts)}, got {snap2.txn_count_total}"
    assert snap2.txn_count_last_1h == len(amounts), \
        "All txns should be in 1h window"
    expected_mean = sum(amounts) / len(amounts)
    assert abs(snap2.mean_txn_amount - expected_mean) < 0.01, \
        f"Mean {snap2.mean_txn_amount:.2f} != {expected_mean:.2f}"
    print(f"     ✓ Profile updated: mean={snap2.mean_txn_amount:.2f}  "
          f"std={snap2.std_txn_amount:.2f}  total={snap2.txn_count_total}")

    # ── Test 3: account_age_days is correct (FIX Bug 1 verification) ─
    # After update_profile, account_age_days must be ~30 days, NOT 0.
    assert snap2.account_age_days > 29.9, \
        f"Bug 1 regression: account_age_days={snap2.account_age_days:.2f} (expected ~30)"
    print(f"     ✓ account_age_days correct: {snap2.account_age_days:.2f}d (Bug 1 fix verified)")

    # ── Test 4: Same-timestamp velocity collision (FIX Bug 2) ─────
    uid_vel = "test_user_collision"
    ps.delete_profile(uid_vel)
    same_ts = time.time()
    # Write 5 txns at the exact same timestamp — in the old code 4 of 5
    # would be silently dropped.
    for _ in range(5):
        ps.update_profile(uid_vel, "dev_A", "1.2.3.4",
                          amount=50.0, now_ts=same_ts)

    snap_vel = ps.get_profile(uid_vel, "dev_A", "1.2.3.4",
                               now_ts=same_ts + 1)
    assert snap_vel.txn_count_last_1h == 5, \
        f"Bug 2 regression: expected 5 txns, got {snap_vel.txn_count_last_1h}"
    print(f"     ✓ Same-timestamp collision fixed: {snap_vel.txn_count_last_1h}/5 counted (Bug 2 fix verified)")

    # ── Test 5: New device detection ─────────────────────────────
    snap3 = ps.get_profile(uid, device_id="dev_NEW", ip="1.2.3.4", now_ts=now)
    assert snap3.is_new_device,    "New device must be flagged"
    assert not snap3.is_new_ip,    "Known IP must not be flagged"
    assert snap3.device_count_seen == 1
    print("     ✓ New device detection correct")

    # ── Test 6: New IP detection ──────────────────────────────────
    snap4 = ps.get_profile(uid, device_id="dev_A", ip="9.9.9.9", now_ts=now)
    assert not snap4.is_new_device, "Known device must not be flagged"
    assert snap4.is_new_ip,         "New IP must be flagged"
    print("     ✓ New IP detection correct")

    # ── Test 7: Velocity windows ──────────────────────────────────
    uid2     = "test_user_velocity"
    ps.delete_profile(uid2)
    base_ts  = time.time() - 7200   # 2 hours ago
    for i in range(10):
        ps.update_profile(uid2, "dev_v", "5.5.5.5",
                          amount=50.0, now_ts=base_ts + i * 300)

    snap5 = ps.get_profile(uid2, "dev_v", "5.5.5.5", now_ts=time.time())
    assert snap5.txn_count_last_1h == 0,  \
        f"Expected 0 in 1h, got {snap5.txn_count_last_1h}"
    assert snap5.txn_count_last_24h == 10, \
        f"Expected 10 in 24h, got {snap5.txn_count_last_24h}"
    print(f"     ✓ Velocity windows: 1h={snap5.txn_count_last_1h}  24h={snap5.txn_count_last_24h}")

    # ── Test 8: Seed demo profiles ────────────────────────────────
    seeded = ps.seed_demo_profiles(DEMO_PROFILES)
    print(f"     ✓ Seeded {seeded} demo profiles")

    snap_demo = ps.get_profile("usr_alex92", "dev_NEW_device", "185.220.0.1")
    assert not snap_demo.is_new_user
    assert snap_demo.is_new_device
    assert snap_demo.is_new_ip
    assert snap_demo.account_age_days > 419, \
        f"Seeded account_age_days wrong: {snap_demo.account_age_days:.1f}"
    print(f"     ✓ Demo usr_alex92: mean={snap_demo.mean_txn_amount:.0f}  "
          f"age={snap_demo.account_age_days:.0f}d  "
          f"new_device={snap_demo.is_new_device}")

    # ── Test 9: to_feature_dict key contract ─────────────────────
    feat = snap_demo.to_feature_dict()
    expected_keys = {
        "is_new_device", "is_new_ip", "device_count_seen",
        "txn_count_last_1h", "txn_count_last_24h", "txn_count_last_7d",
        "inter_txn_seconds", "account_age_days",
        "mean_txn_amount", "std_txn_amount", "txn_count_total",
    }
    assert expected_keys == set(feat.keys()), \
        f"Feature key mismatch: {set(feat.keys())}"
    print(f"     ✓ to_feature_dict keys correct")

    # ── Test 10: get_profile_raw ──────────────────────────────────
    raw = ps.get_profile_raw("usr_alex92")
    assert "welford_mean" in raw, "get_profile_raw must return hash fields"
    print("     ✓ get_profile_raw works")

    # Cleanup
    ps.delete_profile(uid)
    ps.delete_profile(uid2)
    ps.delete_profile(uid_vel)

    print("\n✅  S4 Self-Test PASSED — Profile Store ready for S8 (FastAPI)")
    print("    Next → Stage S8: python backend/main.py\n")


if __name__ == "__main__":
    _self_test()