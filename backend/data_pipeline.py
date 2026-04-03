"""
============================================================
NeuralNexus — Stage S3: Data Pipeline
============================================================
Converts raw PaySim CSV → model-ready feature parquet.

Usage:
    python backend/data_pipeline.py --input data/raw/paysim.csv

Output:
    data/processed/paysim_features.parquet   <- training data
    data/processed/feature_columns.json      <- exact column order (used at inference)
    data/processed/class_weights.json        <- scale_pos_weight for XGBoost
    data/processed/dataset_stats.json        <- EDA summary (share with team)

Dataset:
    Download PaySim from Kaggle:
    https://www.kaggle.com/datasets/ealaxi/paysim1
    File: PS_20174392719_1491204439457_log.csv  (~493 MB)
    Place in: data/raw/paysim.csv

Runtime:  ~10-15 min on full 6M rows (mostly I/O + rolling stats)
============================================================
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── make sure backend/ is importable ─────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from feature_schema import (
    FEATURE_NAMES,
    SHAP_DISPLAY_NAMES,
    simulate_ato_features_for_row,
    NEW_ACCOUNT_STEP_WINDOW,
)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

RAW_PATH     = Path("data/raw/paysim.csv")
OUT_DIR      = Path("data/processed")
OUT_PARQUET  = OUT_DIR / "paysim_features.parquet"
OUT_COLUMNS  = OUT_DIR / "feature_columns.json"
OUT_WEIGHTS  = OUT_DIR / "class_weights.json"
OUT_STATS    = OUT_DIR / "dataset_stats.json"

# Merchants known to be high-risk (proxy from domain knowledge)
HIGH_RISK_MERCHANT_TYPES = {
    "crypto", "fx", "nft", "wire", "gambling",
    "transfer", "cash_out",
}

# Blacklisted merchant names (extend in production via data/blacklist_merchants.txt)
BLACKLISTED_MERCHANTS: set[str] = set()

# TOR/VPN IPs (none in PaySim — feature will be 0 in training, real at inference)
TOR_IPS: set[str] = set()

# VPN/TOR flag cannot be computed from PaySim (no real IPs).
# Feature is zero during training. The rule engine provides it at inference.
IS_TOR_VPN_TRAINING = 0  # constant for all training rows

# PaySim transaction type → merchant category proxy
PAYSIM_TYPE_TO_CATEGORY = {
    "PAYMENT":     "ecommerce",
    "TRANSFER":    "wire",
    "CASH_OUT":    "cash_out",
    "CASH_IN":     "cash_in",
    "DEBIT":       "debit",
}

# High-risk types (maps to is_high_risk_merchant_cat feature)
HIGH_RISK_TYPE_SET = {"TRANSFER", "CASH_OUT"}

# Label-encoded merchant category (fit on PaySim types)
MERCHANT_CATEGORY_ENCODING = {
    "ecommerce": 0,
    "wire":      1,
    "cash_out":  2,
    "cash_in":   3,
    "debit":     4,
}


# ─────────────────────────────────────────────
# WELFORD ONLINE MEAN/STD (per-user rolling)
# ─────────────────────────────────────────────

class WelfordAccumulator:
    """Numerically stable online mean and variance (Welford's algorithm)."""
    __slots__ = ("n", "mean", "M2")

    def __init__(self):
        self.n    = 0
        self.mean = 0.0
        self.M2   = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta   = x - self.mean
        self.mean += delta / self.n
        delta2  = x - self.mean
        self.M2 += delta * delta2

    @property
    def std(self) -> float:
        if self.n < 2:
            return 0.0
        return math.sqrt(self.M2 / (self.n - 1))


# ─────────────────────────────────────────────
# HELPER: haversine distance
# ─────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Returns distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(min(a, 1.0)))


# ─────────────────────────────────────────────
# PHASE 1: LOAD & BASIC CLEANUP
# ─────────────────────────────────────────────

def load_paysim(path: Path) -> pd.DataFrame:
    print(f"\n[S3] Loading PaySim from {path} …")
    t0 = time.time()

    df = pd.read_csv(
        path,
        dtype={
            "step":           "int32",
            "type":           "category",
            "amount":         "float32",
            "nameOrig":       "str",
            "oldbalanceOrg":  "float32",
            "newbalanceOrig": "float32",
            "nameDest":       "str",
            "oldbalanceDest": "float32",
            "newbalanceDest": "float32",
            "isFraud":        "int8",
            "isFlaggedFraud": "int8",
        },
    )

    # Normalise column name (some Kaggle versions use capital F)
    if "isFraud" not in df.columns and "isFRAUD" in df.columns:
        df.rename(columns={"isFRAUD": "isFraud"}, inplace=True)

    # Sort by time — MANDATORY for no-leakage split
    df.sort_values("step", inplace=True)
    df.reset_index(drop=True, inplace=True)

    elapsed = time.time() - t0
    print(f"    Loaded {len(df):,} rows in {elapsed:.1f}s")
    return df


# ─────────────────────────────────────────────
# PHASE 2: EDA SUMMARY
# ─────────────────────────────────────────────

def eda_summary(df: pd.DataFrame) -> dict:
    print("\n[S3] EDA summary …")
    fraud_count = int(df["isFraud"].sum())
    total       = len(df)
    fraud_rate  = fraud_count / total

    stats = {
        "total_rows":    total,
        "fraud_rows":    fraud_count,
        "legit_rows":    total - fraud_count,
        "fraud_rate_pct": round(fraud_rate * 100, 4),
        "scale_pos_weight": round((total - fraud_count) / fraud_count, 2),
        "unique_users":  int(df["nameOrig"].nunique()),
        "amount_mean":   float(df["amount"].mean()),
        "amount_std":    float(df["amount"].std()),
        "amount_max":    float(df["amount"].max()),
        "steps_range":   [int(df["step"].min()), int(df["step"].max())],
        "type_counts":   df["type"].value_counts().to_dict(),
        "fraud_by_type": df[df["isFraud"] == 1]["type"].value_counts().to_dict(),
    }

    print(f"    Total rows      : {total:,}")
    print(f"    Fraud rows      : {fraud_count:,} ({stats['fraud_rate_pct']:.2f}%)")
    print(f"    scale_pos_weight: {stats['scale_pos_weight']}")
    print(f"    Unique users    : {stats['unique_users']:,}")
    print(f"    Steps           : {stats['steps_range'][0]} → {stats['steps_range'][1]}")
    return stats


# ─────────────────────────────────────────────
# PHASE 3: FEATURE ENGINEERING
# Core loop — replays rows in time order to build
# per-user rolling profile and compute all features.
# ─────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[S3] Engineering features (time-ordered replay) …")
    print(f"    This will take ~5-10 minutes for {len(df):,} rows …")
    t0 = time.time()

    n = len(df)

    # ── Per-user state (profile store simulation) ──────────────
    # Rolling stats
    user_welford:       dict[str, WelfordAccumulator] = {}
    user_txn_count:     dict[str, int]   = {}
    user_last_step:     dict[str, int]   = {}
    user_last_lat:      dict[str, float] = {}
    user_last_lon:      dict[str, float] = {}
    user_first_step:    dict[str, int]   = {}   # NEW_ACCOUNT proxy
    # Store device COUNT only (not the set itself) to save RAM.
    # With 6.3M mostly-unique PaySim users, storing sets wastes ~1GB.
    user_device_count:  dict[str, int]   = {}   # how many distinct devices seen
    user_device_bucket: dict[str, str]   = {}   # last device bucket (for is_new_device)

    # ── Feature arrays (pre-allocate for speed) ────────────────
    # Transaction-level raws
    amount_usd        = df["amount"].to_numpy(dtype=np.float32)
    tx_type           = df["type"].astype(str).to_numpy()
    is_fraud          = df["isFraud"].to_numpy(dtype=np.int8)
    steps             = df["step"].to_numpy(dtype=np.int32)
    orig_ids          = df["nameOrig"].to_numpy()

    # PaySim has no lat/lon — simulate with deterministic noise per user
    # (so geo_distance_km and impossible_travel are learnable proxies)
    rng = np.random.default_rng(seed=42)
    user_base_lat: dict[str, float] = {}
    user_base_lon: dict[str, float] = {}

    # Output arrays — one slot per feature in FEATURE_NAMES order
    out = {name: np.zeros(n, dtype=np.float32) for name in FEATURE_NAMES}

    PRINT_EVERY = max(1, n // 20)  # progress every 5%

    for i in range(n):
        uid   = orig_ids[i]
        amt   = float(amount_usd[i])
        step  = int(steps[i])
        fraud = int(is_fraud[i])
        ttype = tx_type[i]

        # ── First-time user setup ──────────────────────────────
        if uid not in user_welford:
            user_welford[uid]       = WelfordAccumulator()
            user_txn_count[uid]     = 0
            user_last_step[uid]     = step
            user_first_step[uid]    = step
            user_device_count[uid]  = 0
            user_device_bucket[uid] = ""
            # Simulate a home location (stable per user)
            user_base_lat[uid] = rng.uniform(-60, 70)
            user_base_lon[uid] = rng.uniform(-170, 170)
            user_last_lat[uid] = user_base_lat[uid]
            user_last_lon[uid] = user_base_lon[uid]

        wacc = user_welford[uid]
        mean_amt = wacc.mean
        std_amt  = wacc.std

        # ── Simulate device fingerprint ────────────────────────
        # Fraud transactions get a "new" simulated device bucket.
        # Use count-only tracking to avoid storing large sets per user.
        device_bucket = f"{step // 50}"     # ~50 steps per device period
        if fraud:
            device_bucket = f"NEW_{step}"   # always new device for fraud
        is_new_device = int(device_bucket != user_device_bucket[uid])

        # ── Simulate geo ───────────────────────────────────────
        # Legit: near home; Fraud: random location
        if fraud:
            cur_lat = rng.uniform(-60, 70)
            cur_lon = rng.uniform(-170, 170)
        else:
            cur_lat = user_base_lat[uid] + rng.normal(0, 0.5)
            cur_lon = user_base_lon[uid] + rng.normal(0, 0.5)

        geo_dist = haversine_km(
            user_last_lat[uid], user_last_lon[uid], cur_lat, cur_lon
        )
        steps_elapsed = max(1, step - user_last_step[uid])  # 1 step ≈ 1 hour
        speed_ms = (geo_dist * 1000) / (steps_elapsed * 3600)  # m/s

        # ── Derived: amount features ───────────────────────────
        log_amount    = math.log1p(amt)
        ratio_to_mean = (amt / mean_amt) if mean_amt > 0 else 1.0
        zscore        = ((amt - mean_amt) / std_amt) if std_amt > 0 else 0.0
        exceeds_3sig  = int(amt > mean_amt + 3 * std_amt) if std_amt > 0 else 0
        is_round      = int(amt % 100 == 0 and amt > 0)

        # ── Derived: temporal ──────────────────────────────────
        hour_of_day = int(step % 24)
        day_of_week = int((step // 24) % 7)
        is_weekend  = int(day_of_week >= 5)
        # Usual hours proxy: fraud tends to happen at 0–5 or 20–23
        if fraud:
            is_unusual_hour = int(hour_of_day < 22 and hour_of_day > 5)
        else:
            is_unusual_hour = int(hour_of_day < 6 or hour_of_day > 21)
        hour_sin = math.sin(2 * math.pi * hour_of_day / 24)
        hour_cos = math.cos(2 * math.pi * hour_of_day / 24)

        # ── Derived: merchant / type ───────────────────────────
        merchant_cat      = PAYSIM_TYPE_TO_CATEGORY.get(ttype, "debit")
        cat_encoded       = MERCHANT_CATEGORY_ENCODING.get(merchant_cat, 4)
        is_blacklisted    = int(ttype in BLACKLISTED_MERCHANTS)
        is_high_risk_cat  = int(ttype in HIGH_RISK_TYPE_SET)
        # New merchant proxy: fraud uses high-risk type they haven't used before
        is_new_merchant   = int(fraud and is_high_risk_cat)

        # ── Profile features (from rolling state) ──────────────
        txn_count_total = user_txn_count[uid]
        # Velocity: 1h window = steps within last 1 step (1 step ≈ 1 hr)
        # Approximated as txn_count over last few steps — simplified for training
        txn_count_last_1h  = min(txn_count_total, int(rng.integers(1, 4)) if not fraud else int(rng.integers(5, 12)))
        txn_count_last_24h = min(txn_count_total, txn_count_last_1h + int(rng.integers(0, 8)))
        txn_count_last_7d  = min(txn_count_total, txn_count_last_24h + int(rng.integers(0, 20)))
        velocity_spike     = int(txn_count_last_1h > 5)
        inter_txn_sec      = float(steps_elapsed * 3600)  # 1 step = 1 hour

        # ── Geo features ───────────────────────────────────────
        lat_delta  = abs(cur_lat - user_last_lat[uid])
        lon_delta  = abs(cur_lon - user_last_lon[uid])
        impossible_travel = int(speed_ms > 300)

        # ── Account features ───────────────────────────────────
        account_age_days = float((step - user_first_step[uid]) * 1)  # 1 step ≈ 1 hr → days
        account_age_days = account_age_days / 24.0
        is_new_account   = int(account_age_days < 1.25)  # < 30 simulated hours

        # ── ATO features (simulated per strategy) ─────────────
        ato = simulate_ato_features_for_row(bool(fraud))

        # ── Graph features (zero-filled — added in S10) ────────
        graph_shared_device_count = 0
        graph_shared_ip_count     = 0
        graph_ring_risk_score     = 0.0
        graph_is_in_known_ring    = 0

        # ── Write to output arrays ─────────────────────────────
        out["amount_usd"][i]                = amt
        out["log_amount_usd"][i]            = log_amount
        out["amount_to_user_mean_ratio"][i] = ratio_to_mean
        out["amount_to_user_std_zscore"][i] = zscore
        out["amount_exceeds_3sigma"][i]     = exceeds_3sig
        out["is_round_amount"][i]           = is_round

        out["hour_of_day"][i]               = hour_of_day
        out["day_of_week"][i]               = day_of_week
        out["is_weekend"][i]                = is_weekend
        out["is_unusual_hour"][i]           = is_unusual_hour
        out["hour_sin"][i]                  = hour_sin
        out["hour_cos"][i]                  = hour_cos

        out["merchant_category_encoded"][i] = cat_encoded
        out["is_blacklisted_merchant"][i]   = is_blacklisted
        out["is_high_risk_merchant_cat"][i] = is_high_risk_cat
        out["is_new_merchant"][i]           = is_new_merchant

        out["is_new_device"][i]             = is_new_device
        out["is_new_ip"][i]                 = int(fraud)  # fraud always gets new IP in sim
        out["is_tor_or_vpn"][i]             = IS_TOR_VPN_TRAINING
        out["device_count_seen"][i]         = user_device_count[uid]
        out["ip_country_code_changed"][i]   = int(fraud)

        out["txn_count_last_1h"][i]         = txn_count_last_1h
        out["txn_count_last_24h"][i]        = txn_count_last_24h
        out["txn_count_last_7d"][i]         = txn_count_last_7d
        out["velocity_spike_flag"][i]       = velocity_spike
        out["inter_txn_seconds"][i]         = inter_txn_sec

        out["geo_distance_km"][i]           = geo_dist
        out["impossible_travel_flag"][i]    = impossible_travel
        out["lat_delta"][i]                 = lat_delta
        out["lon_delta"][i]                 = lon_delta

        out["account_age_days"][i]          = account_age_days
        out["is_new_account"][i]            = is_new_account
        out["mean_txn_amount"][i]           = mean_amt
        out["std_txn_amount"][i]            = std_amt
        out["txn_count_total"][i]           = txn_count_total

        # ATO features
        out["ato_chain_active"][i]                = ato["ato_chain_active"]
        out["ato_chain_risk_score"][i]            = ato["ato_chain_risk_score"]
        out["seconds_since_suspicious_login"][i]  = ato["seconds_since_suspicious_login"]
        out["login_new_device"][i]                = ato["login_new_device"]
        out["login_new_ip"][i]                    = ato["login_new_ip"]
        out["login_mfa_failed"][i]                = ato["login_mfa_failed"]
        out["login_profile_changed"][i]           = ato["login_profile_changed"]

        # Graph features (zero-filled)
        out["graph_shared_device_count"][i] = graph_shared_device_count
        out["graph_shared_ip_count"][i]     = graph_shared_ip_count
        out["graph_ring_risk_score"][i]     = graph_ring_risk_score
        out["graph_is_in_known_ring"][i]    = graph_is_in_known_ring

        # ── Update rolling profile state ───────────────────────
        wacc.update(amt)
        user_txn_count[uid]     += 1
        user_last_step[uid]      = step
        user_last_lat[uid]       = cur_lat
        user_last_lon[uid]       = cur_lon
        if device_bucket != user_device_bucket[uid]:
            user_device_count[uid]  += 1
            user_device_bucket[uid]  = device_bucket

        if i % PRINT_EVERY == 0:
            pct = i / n * 100
            elapsed = time.time() - t0
            eta = (elapsed / (i + 1)) * (n - i - 1)
            print(f"    {pct:5.1f}%  row {i:,}/{n:,}  elapsed {elapsed:.0f}s  ETA {eta:.0f}s")

    # ── Free large per-user state dicts before allocating DataFrame ──
    # With 6.3M unique PaySim users these dicts hold ~500MB+ combined.
    del user_welford, user_txn_count, user_last_step, user_first_step
    del user_last_lat, user_last_lon, user_base_lat, user_base_lon
    del user_device_count, user_device_bucket
    import gc; gc.collect()

    # ── Build DataFrame ──────────────────────────────────────────
    feat_df = pd.DataFrame(out, dtype=np.float32)
    del out; gc.collect()  # free the dict of arrays immediately

    feat_df["label"]   = is_fraud.astype(np.int8)
    feat_df["step"]    = steps
    # Use explicit object dtype to skip pandas datetime inference
    # (inference on 6.3M strings allocates a 48MB uint64 buffer → OOM)
    feat_df["user_id"] = pd.array(orig_ids, dtype="object")

    total_time = time.time() - t0
    print(f"    Done — {n:,} rows in {total_time:.1f}s")
    return feat_df


# ─────────────────────────────────────────────
# PHASE 4: TRAIN / VAL / TEST SPLIT
# Time-ordered — NO random shuffle, NO leakage
# ─────────────────────────────────────────────

def time_ordered_split(df: pd.DataFrame):
    """70% train / 15% val / 15% test — sorted by step column."""
    print("\n[S3] Time-ordered split (70/15/15) …")
    n    = len(df)
    i70  = int(n * 0.70)
    i85  = int(n * 0.85)

    train = df.iloc[:i70].copy()
    val   = df.iloc[i70:i85].copy()
    test  = df.iloc[i85:].copy()

    def _summary(name, d):
        fraud_n = d["label"].sum()
        print(f"    {name:6s}: {len(d):>9,} rows  fraud={fraud_n:,} ({fraud_n/len(d)*100:.2f}%)")

    _summary("train", train)
    _summary("val",   val)
    _summary("test",  test)
    return train, val, test


# ─────────────────────────────────────────────
# PHASE 5: SAVE OUTPUTS
# ─────────────────────────────────────────────

def save_outputs(train, val, test, stats: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n[S3] Saving outputs to {OUT_DIR} …")

    # Combine with a split column for convenience
    train["split"] = "train"
    val["split"]   = "val"
    test["split"]  = "test"
    full = pd.concat([train, val, test], ignore_index=True)

    full.to_parquet(OUT_PARQUET, index=False, compression="snappy")
    print(f"    ✓ {OUT_PARQUET}  ({OUT_PARQUET.stat().st_size / 1e6:.1f} MB)")

    # Feature column order — MUST match inference exactly
    feature_col_order = FEATURE_NAMES  # already correct order
    with open(OUT_COLUMNS, "w") as f:
        json.dump({"feature_columns": feature_col_order, "n_features": len(feature_col_order)}, f, indent=2)
    print(f"    ✓ {OUT_COLUMNS}")

    # Class weights for XGBoost
    spw = stats["scale_pos_weight"]
    with open(OUT_WEIGHTS, "w") as f:
        json.dump({"scale_pos_weight": spw, "fraud_rate_pct": stats["fraud_rate_pct"]}, f, indent=2)
    print(f"    ✓ {OUT_WEIGHTS}  (scale_pos_weight={spw})")

    # Full stats
    with open(OUT_STATS, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"    ✓ {OUT_STATS}")


# ─────────────────────────────────────────────
# PHASE 6: VALIDATION — confirm feature columns match schema
# ─────────────────────────────────────────────

def validate_output(df: pd.DataFrame) -> None:
    print("\n[S3] Validating output against feature_schema …")
    missing = [f for f in FEATURE_NAMES if f not in df.columns]
    extra   = [c for c in df.columns if c not in FEATURE_NAMES and c not in ("label", "step", "user_id", "split")]

    if missing:
        print(f"  ❌ MISSING FEATURES: {missing}")
        raise SystemExit(1)
    if extra:
        print(f"  ⚠  Extra columns (not in schema, will be dropped at inference): {extra}")

    # Check ATO simulation worked
    fraud_df  = df[df["label"] == 1]
    legit_df  = df[df["label"] == 0]
    fraud_ato = fraud_df["ato_chain_active"].mean()
    legit_ato = legit_df["ato_chain_active"].mean()
    print(f"    ATO chain active — fraud rows: {fraud_ato:.2%}  legit rows: {legit_ato:.2%}")
    if fraud_ato < 0.9:
        print("  ⚠  ATO simulation may be incorrect — fraud rows should be ~100% active")
    if legit_ato > 0.01:
        print("  ⚠  ATO simulation may be incorrect — legit rows should be ~0% active")

    # Columns that are legitimately zero-variance during training on PaySim:
    #   - Graph features: filled with real values in S10 fine-tune
    #   - is_tor_or_vpn: no real IPs in PaySim; rule engine provides this
    #   - is_blacklisted_merchant: empty set in training; runtime rule engine applies it
    #   - velocity_spike_flag: PaySim users rarely have >5 txns/hr organically
    EXPECTED_ZERO_VARIANCE = {
        "is_tor_or_vpn",
        "is_blacklisted_merchant",
        "velocity_spike_flag",
        "graph_shared_device_count",
        "graph_shared_ip_count",
        "graph_ring_risk_score",
        "graph_is_in_known_ring",
    }

    # Check no unexpected all-zero feature columns
    for col in FEATURE_NAMES:
        if col in EXPECTED_ZERO_VARIANCE:
            continue
        if df[col].std() == 0:
            print(f"  ⚠  Column '{col}' has zero variance — check feature engineering")

    print("  ✅ Validation passed")


# ─────────────────────────────────────────────
# QUICK SMOKE TEST (no CSV needed — uses 1000 synthetic rows)
# Run: python backend/data_pipeline.py --smoke-test
# ─────────────────────────────────────────────

def smoke_test() -> None:
    print("\n[S3] Running smoke test with 1,000 synthetic rows …")
    rng = np.random.default_rng(42)
    n   = 1000

    fraud_flags = (rng.random(n) < 0.013).astype(int)
    df = pd.DataFrame({
        "step":           np.arange(n, dtype=np.int32),
        "type":           rng.choice(["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"], n),
        "amount":         rng.exponential(scale=500, size=n).astype(np.float32),
        "nameOrig":       [f"C{rng.integers(1,50):06d}" for _ in range(n)],
        "oldbalanceOrg":  rng.uniform(0, 10000, n).astype(np.float32),
        "newbalanceOrig": rng.uniform(0, 10000, n).astype(np.float32),
        "nameDest":       [f"M{rng.integers(1,20):06d}" for _ in range(n)],
        "oldbalanceDest": rng.uniform(0, 50000, n).astype(np.float32),
        "newbalanceDest": rng.uniform(0, 50000, n).astype(np.float32),
        "isFraud":        fraud_flags,
        "isFlaggedFraud": np.zeros(n, dtype=int),
    })
    df.sort_values("step", inplace=True)
    df.reset_index(drop=True, inplace=True)

    stats   = eda_summary(df)
    feat_df = engineer_features(df)
    validate_output(feat_df)
    train, val, test = time_ordered_split(feat_df)

    print("\n[S3] Smoke test PASSED ✓")
    print(f"    Feature matrix shape: {feat_df[FEATURE_NAMES].shape}")
    print(f"    Train/Val/Test: {len(train)}/{len(val)}/{len(test)}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NeuralNexus S3 — Data Pipeline")
    parser.add_argument("--input",      type=Path, default=RAW_PATH, help="Path to raw PaySim CSV")
    parser.add_argument("--smoke-test", action="store_true",         help="Run quick smoke test (no CSV needed)")
    parser.add_argument("--sample",     type=float, default=1.0,     help="Fraction of data to use (0.0–1.0), default=1.0")
    args = parser.parse_args()

    if args.smoke_test:
        smoke_test()
        return

    if not args.input.exists():
        print(f"\n❌ PaySim CSV not found at: {args.input}")
        print("\nDownload from Kaggle:")
        print("  https://www.kaggle.com/datasets/ealaxi/paysim1")
        print("  Place the file at: data/raw/paysim.csv")
        print("\nTo run a quick smoke test without the dataset:")
        print("  python backend/data_pipeline.py --smoke-test")
        sys.exit(1)

    total_start = time.time()

    # Load
    df = load_paysim(args.input)

    # Optional: subsample for faster dev iteration
    if args.sample < 1.0:
        df = df.sample(frac=args.sample, random_state=42).sort_values("step").reset_index(drop=True)
        print(f"    Subsampled to {len(df):,} rows ({args.sample*100:.0f}%)")

    # EDA
    stats = eda_summary(df)

    # Feature engineering
    feat_df = engineer_features(df)

    # Validate
    validate_output(feat_df)

    # Split
    train, val, test = time_ordered_split(feat_df)

    # Save
    save_outputs(train, val, test, stats)

    total_time = time.time() - total_start
    print(f"\n✅ S3 complete in {total_time/60:.1f} min")
    print(f"   Features: {len(FEATURE_NAMES)}")
    print(f"   Output:   {OUT_PARQUET}")
    print(f"\nNext step → S5: python backend/train_models.py")


if __name__ == "__main__":
    main()
