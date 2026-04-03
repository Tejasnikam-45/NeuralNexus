"""
============================================================
NeuralNexus — Stage S8: FastAPI Scoring Engine
============================================================
The main backend server. Loads all model artifacts at startup
and holds them in memory for sub-70ms scoring.

Endpoints
─────────
  POST /score          Score a single transaction (core)
  POST /event          Log a session event (ATO detector feed)
  POST /feedback       Analyst label (false positive / confirm fraud)
  GET  /health         Service health + model metadata
  GET  /model/performance  Eval metrics from training
  GET  /rules          List all active rule engine rules
  GET  /users/{id}     User profile + ATO chain history
  GET  /transactions/recent  Last N scored transactions (for dashboard)
  GET  /stats          Aggregate dashboard stats
  WS   /ws/live        WebSocket live transaction feed

Latency budget (from feature_schema.py):
  Redis read       < 5ms
  Feature compute  < 10ms
  Rule engine      < 5ms
  ML inference     < 30ms
  SHAP compute     < 15ms
  Serialisation    < 5ms
  Total target     < 70ms  (30ms headroom under 100ms SLA)

Usage:
  cd NeuralNexus
  uvicorn backend.main:app --reload --port 8000

Run standalone (dev):
  python backend/main.py
============================================================
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import joblib
import torch

# ── Patch sys.path so relative imports work when run directly ───
_BACKEND_DIR = Path(__file__).parent
_ROOT_DIR    = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── dotenv ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_DIR / ".env")
except ImportError:
    pass

# ── FastAPI ──────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Internal modules ─────────────────────────────────────────────
from feature_schema import (
    FEATURE_NAMES, SHAP_DISPLAY_NAMES, LATENCY_BUDGET_MS,
)
from profile_store import store as profile_store, DEMO_PROFILES
from ato_detector  import ato_detector
from rule_engine   import evaluate_rules, list_rules


# ═══════════════════════════════════════════════════════════════
# AUTOENCODER DEFINITION  (must match train_models.py exactly)
# ═══════════════════════════════════════════════════════════════

class _FraudAutoencoder(torch.nn.Module):
    """
    Architecture must EXACTLY match train_models.py.
    Verified from ae_v1.pt state dict keys:
      encoder.0  Linear(46, 32)  + ReLU
      encoder.3  Linear(32, 16)  + ReLU  (idx 3 = after BN or second ReLU — only Linear+ReLU pairs)
      decoder.0  Linear(16, 32)  + ReLU
      decoder.2  Linear(32, 46)

    Actual key indices from state dict:
      encoder.0.weight / encoder.0.bias  → Linear(input_dim, 32)
      encoder.3.weight / encoder.3.bias  → Linear(32, 16)
      decoder.0.weight / decoder.0.bias  → Linear(16, 32)
      decoder.2.weight / decoder.2.bias  → Linear(32, input_dim)

    Sequential index mapping:
      encoder: [0]=Linear, [1]=ReLU, [2]=Linear, [3]=Linear  ← no, indices must be 0 and 3
      This means: [0]=Linear(46,32), [1]=ReLU, [2]=ReLU(?), [3]=Linear(32,16)
      But simplest match for keys 0 and 3: use a 4-element Sequential where
      index 0 = Linear, 1 = ReLU, 2 = ReLU (or Dropout/BN), 3 = Linear
    """
    def __init__(self, input_dim: int):
        super().__init__()
        # encoder.0 = Linear(input_dim, 32), encoder.3 = Linear(32, 16)
        self.encoder = torch.nn.Sequential(
            torch.nn.Linear(input_dim, 32),  # [0]
            torch.nn.ReLU(),                  # [1]
            torch.nn.ReLU(),                  # [2]  placeholder to get index 3 right
            torch.nn.Linear(32, 16),          # [3]
        )
        # decoder.0 = Linear(16, 32), decoder.2 = Linear(32, input_dim)
        self.decoder = torch.nn.Sequential(
            torch.nn.Linear(16, 32),          # [0]
            torch.nn.ReLU(),                  # [1]
            torch.nn.Linear(32, input_dim),   # [2]
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))


# ═══════════════════════════════════════════════════════════════
# GLOBAL MODEL STORE  (loaded once at startup)
# ═══════════════════════════════════════════════════════════════

class _ModelBundle:
    xgb:           Any = None   # XGBClassifier
    iso:           Any = None   # IsolationForest
    ae:            Any = None   # FraudAutoencoder (torch)
    ae_in_scaler:  Any = None   # StandardScaler  (AE input)
    ae_out_scaler: Any = None   # MinMaxScaler    (AE MSE → 0-1)
    iso_scaler:    Any = None   # MinMaxScaler    (IsoForest score)
    shap_exp:      Any = None   # shap.TreeExplainer
    metadata:      dict = None
    eval_metrics:  dict = None
    feature_names: list[str] = None
    weights:       dict = None
    thresholds:    dict = None
    version:       str = "unknown"
    loaded_at:     float = 0.0


_models = _ModelBundle()

# In-memory ring buffer for recent scored transactions (dashboard)
_RECENT_TXN_MAX = 500
_recent_txns: deque[dict] = deque(maxlen=_RECENT_TXN_MAX)

# In-memory analyst feedback store (flushed to retrain queue)
_feedback_store: list[dict] = []

# WebSocket connection manager
class _WSManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

_ws_manager = _WSManager()


# ═══════════════════════════════════════════════════════════════
# MODEL LOADING
# ═══════════════════════════════════════════════════════════════

def _load_models():
    """Load all model artifacts into memory. Called once at startup."""
    models_dir = _ROOT_DIR / "models"

    t0 = time.perf_counter()
    print("[S8] Loading model artifacts …", flush=True)

    # ── metadata ────────────────────────────────────────────────
    meta_path = models_dir / "model_metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"model_metadata.json not found at {meta_path}")
    _models.metadata = json.loads(meta_path.read_text())
    _models.version  = _models.metadata.get("version", "v1.0.0")

    # Thresholds from metadata (approve < MFA ≤ block)
    _models.thresholds = _models.metadata.get("thresholds", {
        "approve": 40, "mfa": 70, "block": 70
    })
    _models.weights = _models.metadata.get("ensemble_weights", {
        "xgb": 0.60, "iso": 0.25, "ae": 0.15,
    })

    # ── eval metrics ─────────────────────────────────────────────
    eval_path = models_dir / "eval_metrics.json"
    _models.eval_metrics = (
        json.loads(eval_path.read_text()) if eval_path.exists() else {}
    )

    # ── XGBoost ──────────────────────────────────────────────────
    _models.xgb = joblib.load(models_dir / "xgb_v1.pkl")
    print(f"  ✓ XGBoost loaded", flush=True)

    # ── Scalers (iso + ae) ────────────────────────────────────────
    scalers = joblib.load(models_dir / "ensemble_scalers_v1.pkl")
    _models.iso_scaler    = scalers["iso_scaler"]
    _models.ae_in_scaler  = scalers["ae_input_scaler"]   # key saved by train_models.py
    _models.ae_out_scaler = scalers["ae_scaler"]
    _models.feature_names = scalers.get("feature_names", FEATURE_NAMES)
    print(f"  ✓ Scalers loaded  (features={len(_models.feature_names)})", flush=True)

    # ── IsolationForest ───────────────────────────────────────────
    _models.iso = joblib.load(models_dir / "isoforest_v1.pkl")
    print(f"  ✓ IsolationForest loaded", flush=True)

    # ── Autoencoder ───────────────────────────────────────────────
    input_dim = len(_models.feature_names)
    ae = _FraudAutoencoder(input_dim=input_dim)
    ae.load_state_dict(torch.load(
        models_dir / "ae_v1.pt",
        map_location="cpu",
        weights_only=True,
    ))
    ae.eval()
    _models.ae = ae
    print(f"  ✓ Autoencoder loaded  (input_dim={input_dim})", flush=True)

    # ── SHAP explainer ────────────────────────────────────────────
    _models.shap_exp = joblib.load(models_dir / "shap_explainer_v1.pkl")
    print(f"  ✓ SHAP explainer loaded", flush=True)

    _models.loaded_at = time.time()
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[S8] All artifacts loaded in {elapsed:.0f}ms  (version={_models.version})\n",
          flush=True)


# ═══════════════════════════════════════════════════════════════
# FEATURE ENGINEERING  (real-time, per-request)
# ═══════════════════════════════════════════════════════════════

def _build_feature_vector(req: dict, profile_snap, ato_feats: dict) -> pd.DataFrame:
    """
    Assembles the 46-feature vector from:
      1. Transaction payload fields
      2. Derived / computed features
      3. Profile store snapshot
      4. ATO chain detector output

    Returns a single-row DataFrame with columns in FEATURE_NAMES order.
    All missing values are filled with 0.0.
    """
    now_ts  = float(req.get("timestamp_utc", time.time()))
    amount  = float(req.get("amount_usd", 0.0))
    hour    = int(req.get("hour_of_day", 12))
    dow     = int(req.get("day_of_week", 0))
    lat     = float(req.get("latitude",  0.0))
    lon     = float(req.get("longitude", 0.0))

    mean_amt = profile_snap.mean_txn_amount
    std_amt  = profile_snap.std_txn_amount

    # Derived
    ratio   = amount / max(mean_amt, 1.0)
    z_score = (amount - mean_amt) / max(std_amt, 1e-6)
    exceeds_3sigma = int(z_score > 3.0)
    is_round = int(amount > 0 and amount % 100.0 == 0.0)
    is_weekend = int(dow >= 5)
    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)

    # Unusual hour: outside 06:00–22:00
    is_unusual_hour = int(hour < 6 or hour > 21)

    # Velocity spike flag (mirrors rule R02)
    vel_spike = int(profile_snap.txn_count_last_1h > 5)

    # Geo distance & impossible travel
    last_lat = profile_snap.last_lat
    last_lon = profile_snap.last_lon
    geo_km   = _haversine(last_lat, last_lon, lat, lon) if (lat or lon) else 0.0
    inter_s  = profile_snap.inter_txn_seconds
    speed_kmh = (geo_km / max(inter_s, 1.0)) * 3600.0
    impossible_travel = int(speed_kmh > 900.0)
    lat_delta = abs(lat - last_lat)
    lon_delta = abs(lon - last_lon)

    # Merchant
    mcc             = int(req.get("merchant_category_encoded", 0))
    is_blacklisted  = int(req.get("merchant_id", "") in
                          {"merch_blacklisted_1", "merch_blacklisted_2", "merch_crypto_scam_001"})
    HIGH_RISK_MCC   = {6051, 6211, 6050, 7995, 5993, 4829, 6099}
    is_high_risk_mcc = int(mcc in HIGH_RISK_MCC)

    # New merchant: not in user's usual_merchant_categories (simplified)
    # In production: compare against profile.known_mccs set
    is_new_merchant = int(req.get("is_new_merchant", False))

    # TOR / VPN
    ip = str(req.get("ip_address", ""))
    TOR_PREFIXES = {"185.220.", "185.107.", "198.96.", "162.247.", "176.10.", "10.8."}
    is_tor_vpn = int(any(ip.startswith(p) for p in TOR_PREFIXES))

    # Country code changed (simplified: trust the payload flag)
    ip_cc_changed = int(req.get("ip_country_code_changed", False))

    # New account
    is_new_account = int(profile_snap.account_age_days < 30)

    # Graph features (zeros unless graph engine S10 is running)
    graph_shared_device = int(req.get("graph_shared_device_count", 0))
    graph_shared_ip     = int(req.get("graph_shared_ip_count",     0))
    graph_ring_score    = float(req.get("graph_ring_risk_score",   0.0))
    graph_in_ring       = int(req.get("graph_is_in_known_ring",    0))

    # Assemble in FEATURE_NAMES order
    row = {
        "amount_usd":                   amount,
        "log_amount_usd":               math.log1p(amount),
        "amount_to_user_mean_ratio":    ratio,
        "amount_to_user_std_zscore":    z_score,
        "amount_exceeds_3sigma":        exceeds_3sigma,
        "is_round_amount":              is_round,
        "hour_of_day":                  hour,
        "day_of_week":                  dow,
        "is_weekend":                   is_weekend,
        "is_unusual_hour":              is_unusual_hour,
        "hour_sin":                     hour_sin,
        "hour_cos":                     hour_cos,
        "merchant_category_encoded":    mcc,
        "is_blacklisted_merchant":      is_blacklisted,
        "is_high_risk_merchant_cat":    is_high_risk_mcc,
        "is_new_merchant":              is_new_merchant,
        "is_new_device":                int(profile_snap.is_new_device),
        "is_new_ip":                    int(profile_snap.is_new_ip),
        "is_tor_or_vpn":                is_tor_vpn,
        "device_count_seen":            profile_snap.device_count_seen,
        "ip_country_code_changed":      ip_cc_changed,
        "txn_count_last_1h":            profile_snap.txn_count_last_1h,
        "txn_count_last_24h":           profile_snap.txn_count_last_24h,
        "txn_count_last_7d":            profile_snap.txn_count_last_7d,
        "velocity_spike_flag":          vel_spike,
        "inter_txn_seconds":            inter_s,
        "geo_distance_km":              geo_km,
        "impossible_travel_flag":       impossible_travel,
        "lat_delta":                    lat_delta,
        "lon_delta":                    lon_delta,
        "account_age_days":             profile_snap.account_age_days,
        "is_new_account":               is_new_account,
        "mean_txn_amount":              mean_amt,
        "std_txn_amount":               std_amt,
        "txn_count_total":              profile_snap.txn_count_total,
        # ATO features from detector
        "ato_chain_active":             ato_feats["ato_chain_active"],
        "ato_chain_risk_score":         ato_feats["ato_chain_risk_score"],
        "seconds_since_suspicious_login": ato_feats["seconds_since_suspicious_login"],
        "login_new_device":             ato_feats["login_new_device"],
        "login_new_ip":                 ato_feats["login_new_ip"],
        "login_mfa_failed":             ato_feats["login_mfa_failed"],
        "login_profile_changed":        ato_feats["login_profile_changed"],
        # Graph features
        "graph_shared_device_count":    graph_shared_device,
        "graph_shared_ip_count":        graph_shared_ip,
        "graph_ring_risk_score":        graph_ring_score,
        "graph_is_in_known_ring":       graph_in_ring,
    }

    return pd.DataFrame([row], columns=FEATURE_NAMES).fillna(0.0)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlam       = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ═══════════════════════════════════════════════════════════════
# ML ENSEMBLE SCORING
# ═══════════════════════════════════════════════════════════════

def _score_ensemble(X: pd.DataFrame) -> tuple[float, float, float, float]:
    """
    Runs X through the three-model ensemble and returns:
        (xgb_prob, iso_score, ae_score, ensemble_score_0_100)

    Weights: XGB=0.60, IsoForest=0.25, AE=0.15
    """
    w = _models.weights

    # ── XGBoost: probability of fraud ────────────────────────────
    xgb_prob = float(_models.xgb.predict_proba(X)[0][1])

    # ── IsolationForest: anomaly score → [0,1] ───────────────────
    # decision_function returns negative = anomaly. We invert and scale.
    iso_raw   = float(_models.iso.decision_function(X)[0])
    iso_scaled = float(np.clip(
        _models.iso_scaler.transform([[iso_raw]])[0][0], 0.0, 1.0
    ))

    # ── Autoencoder: reconstruction error → [0,1] ─────────────────
    X_tensor  = torch.tensor(
        _models.ae_in_scaler.transform(X.values).astype(np.float32)
    )
    with torch.no_grad():
        recon = _models.ae(X_tensor)
        mse   = float(torch.mean((X_tensor - recon) ** 2).item())
    ae_scaled = float(np.clip(
        _models.ae_out_scaler.transform([[mse]])[0][0], 0.0, 1.0
    ))

    # ── Weighted ensemble → 0-100 score ──────────────────────────
    ensemble = (
        w.get("xgb", 0.60) * xgb_prob +
        w.get("iso", 0.25) * iso_scaled +
        w.get("ae",  0.15) * ae_scaled
    )
    score_100 = round(float(np.clip(ensemble * 100, 0.0, 100.0)), 2)

    return xgb_prob, iso_scaled, ae_scaled, score_100


def _get_shap_reasons(X: pd.DataFrame, n: int = 3) -> list[dict]:
    """
    Returns top-N SHAP feature contributions in human-readable form.
    Uses the pre-loaded TreeExplainer (XGBoost only — fastest).
    """
    try:
        shap_vals = _models.shap_exp.shap_values(X)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1]  # binary: take positive class
        shap_arr  = np.abs(shap_vals[0])
        top_idx   = np.argsort(shap_arr)[::-1][:n]

        reasons = []
        for idx in top_idx:
            feat_name  = FEATURE_NAMES[idx]
            feat_val   = float(X.iloc[0, idx])
            shap_val   = float(shap_vals[0][idx])
            display    = SHAP_DISPLAY_NAMES.get(feat_name, feat_name.replace("_", " ").title())
            direction  = "↑ fraud" if shap_val > 0 else "↓ fraud"
            reasons.append({
                "feature":   feat_name,
                "display":   display,
                "value":     round(feat_val, 4),
                "shap":      round(shap_val, 4),
                "direction": direction,
                "text":      f"{display}: {feat_val:.2f} ({direction})",
            })
        return reasons
    except Exception as e:
        return [{"feature": "shap_error", "display": "SHAP Error", "text": str(e), "shap": 0.0}]


def _make_decision(ml_score: float, rule_output, boost: float) -> tuple[str, float]:
    """
    Combine ML score + rule boost, then apply decision thresholds.
    Rule override always wins over thresholds.

    Returns: (decision, final_score)
    """
    final_score = min(100.0, ml_score + boost)

    # Rule override wins
    if rule_output.override_action == "block":
        return "block",   max(final_score, 80.0)
    if rule_output.override_action == "mfa":
        return "mfa",     max(final_score, 50.0)
    if rule_output.override_action == "approve":
        return "approve", min(final_score, 35.0)

    # Threshold-based decision
    t = _models.thresholds
    if final_score < t.get("approve", 40):
        return "approve", final_score
    if final_score < t.get("mfa", 70):
        return "mfa",     final_score
    return "block",       final_score


# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Load models + seed demo data at startup."""
    _load_models()
    # Seed demo profiles so dashboard stats are non-zero from launch
    seeded = profile_store.seed_demo_profiles(DEMO_PROFILES)
    print(f"[S8] Seeded {seeded} demo profiles into profile store", flush=True)
    print("[S8] NeuralNexus API ready — http://localhost:8000\n", flush=True)
    yield
    # Graceful teardown (nothing needed for now)


app = FastAPI(
    title="NeuralNexus",
    description="Real-time pre-transaction fraud detection API",
    version="1.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class ScoreRequest(BaseModel):
    transaction_id:           str  = Field(default_factory=lambda: f"txn_{uuid.uuid4().hex[:10]}")
    user_id:                  str
    session_id:               str  = ""
    amount_usd:               float
    merchant_id:              str  = ""
    merchant_category_encoded:int  = 0
    ip_address:               str  = ""
    device_id:                str  = ""
    latitude:                 float = 0.0
    longitude:                float = 0.0
    hour_of_day:              int  = 12
    day_of_week:              int  = 0
    timestamp_utc:            Optional[float] = None
    # Optional advanced fields
    is_new_merchant:          bool  = False
    ip_country_code_changed:  bool  = False
    graph_shared_device_count:int   = 0
    graph_shared_ip_count:    int   = 0
    graph_ring_risk_score:    float = 0.0
    graph_is_in_known_ring:   bool  = False


class EventRequest(BaseModel):
    user_id:       str
    session_id:    str
    event_type:    str   # login_ok | login_suspicious | mfa_fail | profile_change | logout
    device_id:     str  = ""
    ip_address:    str  = ""
    latitude:      float = 0.0
    longitude:     float = 0.0
    timestamp_utc: Optional[float] = None
    metadata:      dict = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    transaction_id: str
    user_id:        str
    label:          str   # "fraud" | "legit"
    analyst_id:     str  = "system"
    chain_id:       Optional[str] = None
    notes:          str  = ""


# ═══════════════════════════════════════════════════════════════
# POST /score  — Core scoring endpoint
# ═══════════════════════════════════════════════════════════════

@app.post("/score")
async def score_transaction(req: ScoreRequest, background_tasks: BackgroundTasks):
    """
    Score a transaction in real-time and return a decision.
    Total latency target: < 70ms.
    """
    t_start = time.perf_counter()
    now_ts  = req.timestamp_utc or time.time()
    req_dict = req.model_dump()
    req_dict["timestamp_utc"] = now_ts

    # ── 1. Profile store read (~5ms) ────────────────────────────
    t1 = time.perf_counter()
    profile_snap = profile_store.get_profile(
        user_id=req.user_id,
        device_id=req.device_id,
        ip=req.ip_address,
        now_ts=now_ts,
        lat=req.latitude,
        lon=req.longitude,
    )
    ms_redis = (time.perf_counter() - t1) * 1000

    # ── 2. ATO chain lookup (~1ms) ───────────────────────────────
    t2 = time.perf_counter()
    ato_feats = ato_detector.get_ato_features(req.user_id, req.session_id)
    ms_ato = (time.perf_counter() - t2) * 1000

    # ── 3. Feature vector assembly (~5ms) ───────────────────────
    t3 = time.perf_counter()
    X = _build_feature_vector(req_dict, profile_snap, ato_feats)
    ms_features = (time.perf_counter() - t3) * 1000

    # ── 4. Rule engine (~2ms) ────────────────────────────────────
    t4 = time.perf_counter()
    ctx = {**req_dict, **profile_snap.to_feature_dict(), **ato_feats}
    rule_output = evaluate_rules(ctx)
    ms_rules = (time.perf_counter() - t4) * 1000

    # ── 5. ML ensemble inference (~30ms) ────────────────────────
    t5 = time.perf_counter()
    xgb_prob, iso_score, ae_score, ml_score = _score_ensemble(X)
    ms_ml = (time.perf_counter() - t5) * 1000

    # ── 6. SHAP explanations (~15ms) ─────────────────────────────
    t6 = time.perf_counter()
    shap_reasons = _get_shap_reasons(X, n=3)
    ms_shap = (time.perf_counter() - t6) * 1000

    # ── 7. Decision ───────────────────────────────────────────────
    decision, final_score = _make_decision(ml_score, rule_output, rule_output.total_boost)

    # ── 8. Total latency ─────────────────────────────────────────
    ms_total = (time.perf_counter() - t_start) * 1000

    # ── 9. Build response ─────────────────────────────────────────
    response = {
        "transaction_id": req.transaction_id,
        "user_id":        req.user_id,
        "decision":       decision,
        "score":          round(final_score, 2),
        "ml_score":       round(ml_score, 2),
        "model_scores": {
            "xgb":      round(xgb_prob * 100, 2),
            "iso":      round(iso_score * 100, 2),
            "ae":       round(ae_score  * 100, 2),
        },
        "rule_engine":    rule_output.to_dict(),
        "shap_reasons":   shap_reasons,
        "features": {
            "ato_chain_active":           ato_feats["ato_chain_active"],
            "is_new_device":              int(profile_snap.is_new_device),
            "is_new_ip":                  int(profile_snap.is_new_ip),
            "amount_to_user_mean_ratio":  round(ctx.get("amount_to_user_mean_ratio", 1.0), 3),
            "txn_count_last_1h":          profile_snap.txn_count_last_1h,
        },
        "latency_ms": {
            "redis":    round(ms_redis, 2),
            "ato":      round(ms_ato, 2),
            "features": round(ms_features, 2),
            "rules":    round(ms_rules, 2),
            "ml":       round(ms_ml, 2),
            "shap":     round(ms_shap, 2),
            "total":    round(ms_total, 2),
        },
        "timestamp_utc": now_ts,
        "model_version":  _models.version,
    }

    # ── 10. Background: update profile + broadcast ───────────────
    background_tasks.add_task(
        _post_score_tasks, req, decision, final_score, response, now_ts
    )

    return response


def _post_score_tasks(req: ScoreRequest, decision: str, score: float,
                      response: dict, now_ts: float):
    """
    Runs after the response is sent — no impact on latency.
    Must be a regular (sync) function: FastAPI BackgroundTasks.add_task()
    does not support coroutines. WebSocket broadcast is scheduled via
    asyncio.run_coroutine_threadsafe so it still reaches connected clients.
    """
    # Update behavioral profile for next transaction
    profile_store.update_profile(
        user_id=req.user_id,
        device_id=req.device_id,
        ip=req.ip_address,
        amount=req.amount_usd,
        now_ts=now_ts,
        lat=req.latitude,
        lon=req.longitude,
    )

    # Add to recent transactions ring buffer
    _recent_txns.appendleft({
        "transaction_id": req.transaction_id,
        "user_id":        req.user_id,
        "amount_usd":     req.amount_usd,
        "decision":       decision,
        "score":          score,
        "timestamp_utc":  now_ts,
        "shap_reasons":   response["shap_reasons"][:2],
        "rule_triggers":  [r["rule_id"] for r in response["rule_engine"]["triggered_rules"]],
    })

    # WebSocket broadcast — schedule on the running event loop
    payload = {
        "type": "transaction",
        "data": {
            "transaction_id": req.transaction_id,
            "user_id":        req.user_id,
            "amount_usd":     req.amount_usd,
            "decision":       decision,
            "score":          score,
            "timestamp_utc":  now_ts,
            "top_reason":     response["shap_reasons"][0]["text"] if response["shap_reasons"] else "",
        }
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_ws_manager.broadcast(payload))
    except RuntimeError:
        pass  # No event loop — WebSocket not available (e.g. unit tests)


# ═══════════════════════════════════════════════════════════════
# POST /event  — Session event logging (ATO feed)
# ═══════════════════════════════════════════════════════════════

@app.post("/event")
async def log_session_event(req: EventRequest):
    """
    Log a session event (login, MFA failure, profile change).
    ATO detector will open a chain if the event is high-risk.
    """
    result = ato_detector.log_event(req.model_dump())

    if result["ato_chain_opened"]:
        await _ws_manager.broadcast({
            "type": "ato_chain",
            "data": {
                "chain_id":   result["ato_chain_id"],
                "user_id":    req.user_id,
                "event_type": req.event_type,
                "timestamp":  req.timestamp_utc or time.time(),
            }
        })

    return result


# ═══════════════════════════════════════════════════════════════
# POST /feedback  — Analyst labelling
# ═══════════════════════════════════════════════════════════════

@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """
    Analyst marks a transaction as 'fraud' or 'legit'.
    Stored for adaptive retraining (Stage S11).
    If chain_id is provided, the ATO chain is resolved.
    """
    if req.label not in ("fraud", "legit"):
        raise HTTPException(status_code=400, detail="label must be 'fraud' or 'legit'")

    label_entry = {
        "transaction_id": req.transaction_id,
        "user_id":        req.user_id,
        "label":          req.label,
        "analyst_id":     req.analyst_id,
        "notes":          req.notes,
        "labeled_at":     time.time(),
    }
    _feedback_store.append(label_entry)

    chain_resolved = False
    if req.chain_id:
        chain_resolved = ato_detector.resolve_chain(req.chain_id)

    return {
        "status":          "accepted",
        "transaction_id":  req.transaction_id,
        "label":           req.label,
        "total_labels":    len(_feedback_store),
        "chain_resolved":  chain_resolved,
    }


# ═══════════════════════════════════════════════════════════════
# GET /health
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    """Service health + model version. Used by monitoring and demo judges."""
    redis_ok = profile_store.ping()
    uptime   = round(time.time() - _models.loaded_at, 1) if _models.loaded_at else 0

    return {
        "status":        "healthy" if _models.xgb is not None else "degraded",
        "model_version": _models.version,
        "uptime_seconds": uptime,
        "redis_ok":       redis_ok,
        "recent_txn_count": len(_recent_txns),
        "pending_labels":   len(_feedback_store),
        "ws_connections":   len(_ws_manager._connections),
    }


# ═══════════════════════════════════════════════════════════════
# GET /model/performance
# ═══════════════════════════════════════════════════════════════

@app.get("/model/performance")
def model_performance():
    """Returns training eval metrics + runtime model config."""
    return {
        "eval_metrics": _models.eval_metrics,
        "ensemble_weights": _models.weights,
        "thresholds":       _models.thresholds,
        "feature_count":    len(_models.feature_names or []),
        "model_version":    _models.version,
    }


# ═══════════════════════════════════════════════════════════════
# GET /rules
# ═══════════════════════════════════════════════════════════════

@app.get("/rules")
def get_rules():
    """Lists all active rule engine rules with metadata."""
    return {"rules": list_rules(), "count": len(list_rules())}


# ═══════════════════════════════════════════════════════════════
# GET /users/{user_id}
# ═══════════════════════════════════════════════════════════════

@app.get("/users/{user_id}")
def get_user_profile(user_id: str):
    """Returns user's behavioral profile + ATO chain history."""
    snap    = profile_store.get_profile(user_id, "", "")
    raw     = profile_store.get_profile_raw(user_id)
    chains  = ato_detector.get_chain_history(user_id, limit=10)

    return {
        "user_id":      user_id,
        "is_new_user":  snap.is_new_user,
        "profile": {
            "mean_txn_amount":   round(snap.mean_txn_amount, 2),
            "std_txn_amount":    round(snap.std_txn_amount, 2),
            "txn_count_total":   snap.txn_count_total,
            "account_age_days":  round(snap.account_age_days, 1),
            "device_count_seen": snap.device_count_seen,
            "txn_count_last_1h":  snap.txn_count_last_1h,
            "txn_count_last_24h": snap.txn_count_last_24h,
            "txn_count_last_7d":  snap.txn_count_last_7d,
        },
        "ato_chain_history": chains,
        "raw_redis": raw,
    }


# ═══════════════════════════════════════════════════════════════
# GET /transactions/recent
# ═══════════════════════════════════════════════════════════════

@app.get("/transactions/recent")
def get_recent_transactions(limit: int = 50):
    """Returns last N scored transactions for the live dashboard feed."""
    limit = min(limit, _RECENT_TXN_MAX)
    return {
        "transactions": list(_recent_txns)[:limit],
        "count":        min(len(_recent_txns), limit),
    }


# ═══════════════════════════════════════════════════════════════
# GET /stats  — Dashboard aggregate stats
# ═══════════════════════════════════════════════════════════════

@app.get("/stats")
def get_stats():
    """Aggregate stats for the dashboard KPI cards."""
    txns = list(_recent_txns)
    if not txns:
        return {
            "total_scored": 0,
            "approved": 0, "mfa": 0, "blocked": 0,
            "block_rate_pct": 0.0,
            "avg_score": 0.0,
            "avg_latency_ms": None,
        }

    decisions = [t["decision"] for t in txns]
    scores    = [t["score"]    for t in txns]

    return {
        "total_scored":  len(txns),
        "approved":      decisions.count("approve"),
        "mfa":           decisions.count("mfa"),
        "blocked":       decisions.count("block"),
        "block_rate_pct": round(decisions.count("block") / len(txns) * 100, 2),
        "avg_score":     round(sum(scores) / len(scores), 2),
        "active_ato_chains": len(ato_detector.get_active_chains()),
        "pending_analyst_labels": len(_feedback_store),
    }


# ═══════════════════════════════════════════════════════════════
# GET /ato/chains  — Active ATO chains list
# ═══════════════════════════════════════════════════════════════

@app.get("/ato/chains")
def get_ato_chains():
    """Returns all open ATO chains for the ATO Chains page."""
    chains = ato_detector.get_active_chains()
    return {"chains": chains, "count": len(chains)}


# ═══════════════════════════════════════════════════════════════
# GET /feedback/queue  — Analyst review queue
# ═══════════════════════════════════════════════════════════════

@app.get("/feedback/queue")
def get_feedback_queue(limit: int = 100):
    """
    Returns blocked + MFA transactions awaiting analyst review.
    This is what the Analyst Review page actually needs — not already-labeled items.
    Analysts see blocked txns and decide: confirm fraud OR mark false positive.
    """
    review_queue = [
        t for t in _recent_txns
        if t["decision"] in ("block", "mfa")
    ]
    return {
        "queue":        list(review_queue)[:limit],
        "count":        len(review_queue),
        "total_labels": len(_feedback_store),
    }


# ═══════════════════════════════════════════════════════════════
# DELETE /feedback/clear  — Demo helper only
# ═══════════════════════════════════════════════════════════════

@app.delete("/feedback/clear")
def clear_feedback():
    """Demo helper: clears the in-memory feedback store."""
    _feedback_store.clear()
    return {"status": "cleared"}


# ═══════════════════════════════════════════════════════════════
# WS /ws/live  — WebSocket live transaction stream
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/live")
async def ws_live_feed(websocket: WebSocket):
    """
    WebSocket endpoint for the live dashboard feed.
    Pushes transaction and ATO chain events as they arrive.
    """
    await _ws_manager.connect(websocket)
    try:
        # Send immediate snapshot of recent transactions on connect
        await websocket.send_json({
            "type": "snapshot",
            "data": list(_recent_txns)[:20],
        })
        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
    except Exception:
        _ws_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════════
# POST /simulate  — Demo fraud simulator
# ═══════════════════════════════════════════════════════════════

@app.post("/simulate")
async def simulate_transactions(
    n: int = 10,
    fraud_pct: float = 0.3,
    background_tasks: BackgroundTasks = None,
):
    """
    Demo helper: fires N synthetic transactions through /score, with
    fraud_pct fraction designed to be high-risk.
    Perfect for the fraud simulator page during demos.
    """
    import random

    DEMO_USERS = [p["user_id"] for p in DEMO_PROFILES]
    results    = []

    for i in range(max(1, min(n, 100))):
        is_fraud = random.random() < fraud_pct
        user_id  = random.choice(DEMO_USERS)
        amount   = random.uniform(5_000, 50_000) if is_fraud else random.uniform(50, 2_000)
        hour     = random.choice([2, 3, 4]) if is_fraud else random.randint(9, 20)

        mock_req = ScoreRequest(
            user_id=user_id,
            session_id=f"sess_sim_{uuid.uuid4().hex[:8]}",
            amount_usd=amount,
            hour_of_day=hour,
            day_of_week=random.randint(0, 6),
            device_id="dev_new_unknown" if is_fraud else f"dev_known_{user_id[-3:]}",
            ip_address="185.220.10.99" if is_fraud else "203.0.113.10",
            merchant_id="merch_amazon" if not is_fraud else "merch_crypto_scam_001",
            merchant_category_encoded=6051 if is_fraud else 5411,
            # ato_chain_active is NOT a ScoreRequest field — ATO is driven
            # by /event log calls, not the transaction payload itself.
            timestamp_utc=time.time(),
        )

        # Fire /score internally
        resp = await score_transaction(
            mock_req,
            BackgroundTasks() if background_tasks is None else background_tasks,
        )
        results.append({
            "transaction_id": resp["transaction_id"],
            "user_id": user_id,
            "amount_usd": amount,
            "decision": resp["decision"],
            "score": resp["score"],
            "simulated_fraud": is_fraud,
        })

    return {
        "simulated": len(results),
        "results":   results,
        "summary": {
            "blocked": sum(1 for r in results if r["decision"] == "block"),
            "mfa":     sum(1 for r in results if r["decision"] == "mfa"),
            "approved": sum(1 for r in results if r["decision"] == "approve"),
        }
    }


# ═══════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "service":  "NeuralNexus Fraud Detection API",
        "version":  _models.version,
        "docs":     "/docs",
        "health":   "/health",
        "status":   "operational",
    }


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,       # single worker so model state is shared
        log_level="info",
    )
