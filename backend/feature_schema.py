"""
============================================================
NeuralNexus — Feature Contract  (feature_schema.py)
============================================================
SINGLE SOURCE OF TRUTH for every feature.

Rules:
  1. Add a feature here FIRST before using it anywhere.
  2. Training pipeline reads TRAINING_FEATURES to build X.
  3. Inference pipeline reads INFERENCE_FEATURES to build
     the real-time feature vector — must match exactly.
  4. The lists must produce the same column order.
  5. Never rename a feature without updating both lists.

Run self-check:
  python feature_schema.py   → prints validation result
============================================================
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


# ─────────────────────────────────────────────
# FEATURE DESCRIPTOR
# ─────────────────────────────────────────────

@dataclass
class Feature:
    name: str
    dtype: Literal["float32", "int32", "bool", "category"]
    source: Literal["transaction", "profile", "ato", "graph", "derived"]
    description: str
    null_strategy: Literal["zero", "mean", "median", "flag"] = "zero"
    # "transaction" = comes directly from the API request payload
    # "profile"     = computed from Redis behavioral profile
    # "ato"         = from ATO chain detector
    # "graph"       = from NetworkX fraud graph
    # "derived"     = computed on-the-fly from combinations


# ─────────────────────────────────────────────
# MASTER FEATURE LIST
# Order here = column order in model's X matrix
# ─────────────────────────────────────────────

ALL_FEATURES: list[Feature] = [

    # ── Transaction-level raw features ──────────────
    Feature("amount_usd",               "float32", "transaction",
            "Raw transaction amount in USD"),

    Feature("log_amount_usd",           "float32", "derived",
            "log1p(amount_usd) — compresses heavy tail"),

    Feature("amount_to_user_mean_ratio","float32", "derived",
            "amount / profile.mean_txn_amount — key ATO signal",
            null_strategy="mean"),

    Feature("amount_to_user_std_zscore","float32", "derived",
            "(amount - mean) / std — standardized deviation",
            null_strategy="zero"),

    Feature("amount_exceeds_3sigma",    "bool",    "derived",
            "1 if amount > mean + 3*std"),

    Feature("is_round_amount",          "bool",    "derived",
            "1 if amount is a round number (fraud pattern)"),

    # ── Temporal features ───────────────────────────
    Feature("hour_of_day",              "int32",   "transaction",
            "0–23 UTC hour of transaction"),

    Feature("day_of_week",              "int32",   "transaction",
            "0=Monday … 6=Sunday"),

    Feature("is_weekend",               "bool",    "derived",
            "1 if Saturday or Sunday"),

    Feature("is_unusual_hour",          "bool",    "derived",
            "1 if hour not in profile.usual_hours"),

    Feature("hour_sin",                 "float32", "derived",
            "sin(2π * hour/24) — cyclic encoding"),

    Feature("hour_cos",                 "float32", "derived",
            "cos(2π * hour/24) — cyclic encoding"),

    # ── Merchant features ────────────────────────────
    Feature("merchant_category_encoded","int32",   "transaction",
            "Label-encoded MCC category (fit on training data)"),

    Feature("is_blacklisted_merchant",  "bool",    "derived",
            "1 if merchant in blacklist lookup table"),

    Feature("is_high_risk_merchant_cat","bool",    "derived",
            "1 if MCC in {crypto, FX, NFT, wire, gambling}"),

    Feature("is_new_merchant",          "bool",    "derived",
            "1 if merchant not in profile.usual_merchant_categories"),

    # ── Device / IP features ─────────────────────────
    Feature("is_new_device",            "bool",    "profile",
            "1 if device_id NOT in profile.known_devices"),

    Feature("is_new_ip",                "bool",    "profile",
            "1 if ip_address NOT in profile.known_ips"),

    Feature("is_tor_or_vpn",            "bool",    "derived",
            "1 if IP in TOR exit node or known VPN range list"),

    Feature("device_count_seen",        "int32",   "profile",
            "Total distinct devices in user profile",
            null_strategy="zero"),

    Feature("ip_country_code_changed",  "bool",    "derived",
            "1 if IP geolocation country != usual countries"),

    # ── Velocity features (profile store) ────────────
    Feature("txn_count_last_1h",        "int32",   "profile",
            "User transaction count in past 1 hour",
            null_strategy="zero"),

    Feature("txn_count_last_24h",       "int32",   "profile",
            "User transaction count in past 24 hours",
            null_strategy="zero"),

    Feature("txn_count_last_7d",        "int32",   "profile",
            "User transaction count in past 7 days",
            null_strategy="zero"),

    Feature("velocity_spike_flag",      "bool",    "derived",
            "1 if txn_count_last_1h > 5 (hard rule mirrors rule engine)"),

    Feature("inter_txn_seconds",        "float32", "profile",
            "Seconds since user's last transaction",
            null_strategy="median"),

    # ── Geolocation features ─────────────────────────
    Feature("geo_distance_km",          "float32", "derived",
            "Haversine distance from last known location",
            null_strategy="zero"),

    Feature("impossible_travel_flag",   "bool",    "derived",
            "1 if geo_distance_km / inter_txn_seconds > ~300m/s"),

    Feature("lat_delta",                "float32", "derived",
            "Absolute latitude change from last transaction",
            null_strategy="zero"),

    Feature("lon_delta",                "float32", "derived",
            "Absolute longitude change from last transaction",
            null_strategy="zero"),

    # ── Account-level profile features ───────────────
    Feature("account_age_days",         "float32", "profile",
            "Age of account in days at transaction time",
            null_strategy="mean"),

    Feature("is_new_account",           "bool",    "derived",
            "1 if account_age_days < 30"),

    Feature("mean_txn_amount",          "float32", "profile",
            "Rolling mean transaction amount from profile",
            null_strategy="mean"),

    Feature("std_txn_amount",           "float32", "profile",
            "Rolling std of transaction amounts from profile",
            null_strategy="mean"),

    Feature("txn_count_total",          "int32",   "profile",
            "Total lifetime transaction count",
            null_strategy="zero"),

    # ── ATO Chain features ───────────────────────────
    Feature("ato_chain_active",         "bool",    "ato",
            "1 if transaction occurs within open ATO chain window"),

    Feature("ato_chain_risk_score",     "float32", "ato",
            "Risk score of the triggering login event (0 if no chain)",
            null_strategy="zero"),

    Feature("seconds_since_suspicious_login", "float32", "ato",
            "Seconds elapsed since suspicious login event (9999 if no chain)",
            null_strategy="zero"),

    Feature("login_new_device",         "bool",    "ato",
            "1 if triggering login used a new device"),

    Feature("login_new_ip",             "bool",    "ato",
            "1 if triggering login used a new IP"),

    Feature("login_mfa_failed",         "bool",    "ato",
            "1 if MFA failed during triggering login event"),

    Feature("login_profile_changed",    "bool",    "ato",
            "1 if profile data changed between login and transaction"),

    # ── Graph features (NetworkX) ────────────────────
    Feature("graph_shared_device_count","int32",   "graph",
            "Number of other users sharing same device in fraud graph",
            null_strategy="zero"),

    Feature("graph_shared_ip_count",    "int32",   "graph",
            "Number of other users sharing same IP",
            null_strategy="zero"),

    Feature("graph_ring_risk_score",    "float32", "graph",
            "Max risk score within the user's fraud ring community",
            null_strategy="zero"),

    Feature("graph_is_in_known_ring",   "bool",    "graph",
            "1 if user is part of a flagged Louvain community"),

]


# ─────────────────────────────────────────────
# NAMED SUBLISTS  (import these in your code)
# ─────────────────────────────────────────────

# All feature names in model-column order
FEATURE_NAMES: list[str] = [f.name for f in ALL_FEATURES]

# Features available at training time (from PaySim + engineered)
# Graph features excluded if graph not run during training
TRAINING_FEATURES: list[str] = FEATURE_NAMES  # all features

# Features available at inference time (real-time scoring)
# Must be identical order to TRAINING_FEATURES
INFERENCE_FEATURES: list[str] = FEATURE_NAMES  # must match

# Features that require Redis profile lookup
PROFILE_FEATURES: list[str] = [
    f.name for f in ALL_FEATURES if f.source == "profile"
]

# Features that require ATO chain detector
ATO_FEATURES: list[str] = [
    f.name for f in ALL_FEATURES if f.source == "ato"
]

# Features that require NetworkX graph lookup
GRAPH_FEATURES: list[str] = [
    f.name for f in ALL_FEATURES if f.source == "graph"
]

# SHAP-friendly display names (maps feature name → human label)
SHAP_DISPLAY_NAMES: dict[str, str] = {
    "amount_to_user_mean_ratio":      "Amount vs. User Average",
    "amount_exceeds_3sigma":          "Amount 3σ Outlier",
    "is_new_device":                  "New Device Fingerprint",
    "is_new_ip":                      "New IP Address",
    "is_tor_or_vpn":                  "TOR / VPN Detected",
    "ato_chain_active":               "ATO Chain Signal",
    "velocity_spike_flag":            "Velocity Spike (>5/hr)",
    "impossible_travel_flag":         "Impossible Travel",
    "is_blacklisted_merchant":        "Blacklisted Merchant",
    "is_high_risk_merchant_cat":      "High-Risk Merchant Category",
    "is_new_merchant":                "New Merchant",
    "is_unusual_hour":                "Unusual Transaction Hour",
    "geo_distance_km":                "Geographic Distance",
    "is_new_account":                 "New Account (<30 days)",
    "graph_is_in_known_ring":         "Member of Fraud Ring",
    "login_mfa_failed":               "MFA Failure on Login",
    "login_profile_changed":          "Profile Changed After Login",
    "seconds_since_suspicious_login": "Time Since Suspicious Login",
}

# Latency budget (milliseconds) — enforced in Stage 6 / S8
LATENCY_BUDGET_MS = {
    "redis_read":       5,    # profile store lookup
    "feature_compute":  10,   # all derived features
    "rule_engine":      5,    # hard rules pass
    "ml_inference":     30,   # XGB + IsoForest + AE ensemble
    "shap_compute":     15,   # SHAP TreeExplainer (pre-cached on train)
    "serialization":    5,    # JSON response
    "total_target":     70,   # target — leaves 30ms buffer under 100ms SLA
    "sla":              100,  # hard SLA limit
}

# ─────────────────────────────────────────────
# ATO FEATURE SIMULATION STRATEGY  (Stage S3)
# ─────────────────────────────────────────────
# During training we don't have real login events from PaySim.
# We simulate ATO features as follows to ensure the model
# learns them as a meaningful fraud signal.
# WARNING: If you use all-zeros for ATO features on fraud rows,
# the model will learn to IGNORE them entirely.
import random

def simulate_ato_features_for_row(is_fraud: bool) -> dict:
    """
    Called once per PaySim row during Stage S3 feature engineering.
    Returns a dict of ATO feature values to inject into the feature matrix.

    Strategy:
      - Fraud rows   → High chance of ATO chain active
      - Legit rows   → Small chance of false-positive ATO chain
    """
    if is_fraud:
        chain_active = 1 if random.random() < 0.85 else 0
        return {
            "ato_chain_active":               chain_active,
            "ato_chain_risk_score":           random.uniform(65, 95) if chain_active else 0.0,
            "seconds_since_suspicious_login": random.uniform(5, 280) if chain_active else 9999.0,
            "login_new_device":               1 if chain_active else 0,
            "login_new_ip":                   random.randint(0, 1) if chain_active else 0,
            "login_mfa_failed":               1 if chain_active else 0,
            "login_profile_changed":          random.randint(0, 1) if chain_active else 0,
        }
    else:
        chain_active = 1 if random.random() < 0.02 else 0  # 2% false positive rate
        return {
            "ato_chain_active":               chain_active,
            "ato_chain_risk_score":           random.uniform(40, 75) if chain_active else 0.0,
            "seconds_since_suspicious_login": random.uniform(200, 3000) if chain_active else 9999.0,
            "login_new_device":               random.randint(0, 1) if chain_active else 0,
            "login_new_ip":                   random.randint(0, 1) if chain_active else 0,
            "login_mfa_failed":               0,
            "login_profile_changed":          0,
        }


# ─────────────────────────────────────────────
# SYNTHETIC IDENTITY — ACCOUNT AGE PROXY (Stage S9)
# ─────────────────────────────────────────────
# PaySim has NO account creation date column.
# Proxy: use the FIRST transaction timestamp per nameOrig as the
# account creation event.
# "New account" = nameOrig whose first_tx_step is within the last
# NEW_ACCOUNT_STEP_WINDOW steps of the dataset.
# Document this assumption in README — judges will ask.
NEW_ACCOUNT_STEP_WINDOW = 30  # PaySim "steps" (each = 1 simulated hour)

# ─────────────────────────────────────────────
# OPTUNA TRAINING CONFIG (Stage S5)
# ─────────────────────────────────────────────
# 50 trials on 6M rows = 2–4 hours. Use 20 trials on 20% sample instead.
OPTUNA_N_TRIALS     = 20
OPTUNA_SAMPLE_FRAC  = 0.20   # 20% stratified sample for hyperparameter search
# After finding best params, refit on FULL dataset (1 final fit, no CV).

# ─────────────────────────────────────────────
# ATO CHAIN WINDOW CONFIG (Stage S6)
# ─────────────────────────────────────────────
import os
# 300s for demo mode (judges need time to see the ATO Chains page update).
# 30s for production (real-time, strict).
# Set env var ATO_WINDOW_SECONDS=30 to switch to production mode.
ATO_WINDOW_SECONDS = int(os.getenv("ATO_WINDOW_SECONDS", "300"))

# ─────────────────────────────────────────────
# RETRAINING CONFIG (Stage S11)
# ─────────────────────────────────────────────
# 50 labels minimum in production, but 50 will never trigger in a
# 4-hour hackathon demo. Use RETRAIN_MIN_LABELS=10 for demo mode.
RETRAIN_MIN_LABELS = int(os.getenv("RETRAIN_MIN_LABELS", "10"))


# ─────────────────────────────────────────────
# SELF-VALIDATION
# ─────────────────────────────────────────────

def validate_schema() -> None:
    """Run this to catch schema mismatches before training or deploying."""
    errors = []

    # Check no duplicate feature names
    names = [f.name for f in ALL_FEATURES]
    dupes = [n for n in names if names.count(n) > 1]
    if dupes:
        errors.append(f"Duplicate feature names: {set(dupes)}")

    # Check training and inference lists are identical
    if TRAINING_FEATURES != INFERENCE_FEATURES:
        errors.append("TRAINING_FEATURES != INFERENCE_FEATURES — model will fail at inference!")

    # Check latency budget sums to < SLA
    budget_sum = sum(v for k, v in LATENCY_BUDGET_MS.items()
                     if k not in ("total_target", "sla"))
    if budget_sum > LATENCY_BUDGET_MS["sla"]:
        errors.append(f"Latency budget exceeds SLA: {budget_sum}ms > {LATENCY_BUDGET_MS['sla']}ms")

    if errors:
        print("❌ Schema validation FAILED:")
        for e in errors:
            print(f"   • {e}")
        raise SystemExit(1)
    else:
        print(f"✅ Schema valid — {len(ALL_FEATURES)} features, "
              f"budget target {LATENCY_BUDGET_MS['total_target']}ms / SLA {LATENCY_BUDGET_MS['sla']}ms")


if __name__ == "__main__":
    validate_schema()
    print("\nFeature sources breakdown:")
    for src in ("transaction", "profile", "ato", "graph", "derived"):
        count = sum(1 for f in ALL_FEATURES if f.source == src)
        print(f"  {src:12s}: {count} features")
    print(f"\nTotal features: {len(ALL_FEATURES)}")
