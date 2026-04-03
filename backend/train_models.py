"""
============================================================
NeuralNexus — Stage S5: ML Model Training
============================================================
Trains the three-model ensemble:
1. XGBoost Classifier (Supervised) — optimized via Optuna
2. Isolation Forest (Unsupervised) — fits on all data with contamination set to fraud rate
3. Autoencoder (Unsupervised) — fits only on legitimate transactions to learn normal state, uses PyTorch

Artifacts saved to models/:
- XGBoost: xgb_v1.pkl
- IsoForest: isoforest_v1.pkl
- Autoencoder: ae_v1.pt
- Scalers/Ensemble: ensemble_scalers_v1.pkl (contains AE StandardScaler, and MinMaxScalers for IF/AE)
- SHAP: shap_explainer_v1.pkl

Usage:
    python backend/train_models.py
============================================================
"""

import json
import math
import os
import sys
import time
import warnings
from pathlib import Path

import joblib
import mlflow
import numpy as np
import optuna
import pandas as pd
import shap
import torch
import torch.nn as nn
import torch.optim as optim
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from torch.utils.data import DataLoader, TensorDataset

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)

# ── make sure backend/ is importable
sys.path.insert(0, str(Path(__file__).parent))
from feature_schema import FEATURE_NAMES, OPTUNA_N_TRIALS, OPTUNA_SAMPLE_FRAC

# ─────────────────────────────────────────────
# CONSTANTS & PATHS
# ─────────────────────────────────────────────

DATA_DIR    = Path("data/processed")
DATA_FILE   = DATA_DIR / "paysim_features.parquet"
WEIGHT_FILE = DATA_DIR / "class_weights.json"
MODELS_DIR  = Path("models")

XGB_PATH    = MODELS_DIR / "xgb_v1.pkl"
ISO_PATH    = MODELS_DIR / "isoforest_v1.pkl"
AE_PATH     = MODELS_DIR / "ae_v1.pt"
SCALER_PATH = MODELS_DIR / "ensemble_scalers_v1.pkl"
SHAP_PATH   = MODELS_DIR / "shap_explainer_v1.pkl"

MLFLOW_URI  = os.environ.get("MLFLOW_TRACKING_URI", "file:./mlruns")

# Ensemble Weights
W_XGB = 0.60
W_ISO = 0.25
W_AE  = 0.15

# PyTorch Device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─────────────────────────────────────────────
# PyTorch AUTOENCODER MODEL
# ─────────────────────────────────────────────

class FraudAutoencoder(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        # Simple funnel architecture
        hidden_1 = max(16, input_dim // 2)
        hidden_2 = max(8, input_dim // 4)
        
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_1),
            nn.ReLU(),
            nn.Linear(hidden_1, hidden_2),
            nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.Linear(hidden_2, hidden_1),
            nn.ReLU(),
            nn.Linear(hidden_1, input_dim)
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


# ─────────────────────────────────────────────
# PHASE 1: LOAD DATA
# ─────────────────────────────────────────────

def load_data():
    print(f"\n[S5] Loading data from {DATA_FILE} ...")
    t0 = time.time()
    
    if not DATA_FILE.exists():
        print(f"❌ Error: {DATA_FILE} not found. Did you run Stage S3?")
        sys.exit(1)
        
    df = pd.read_parquet(DATA_FILE)
    
    with open(WEIGHT_FILE, "r") as f:
        w_data = json.load(f)
        scale_pos_weight = w_data["scale_pos_weight"]
        fraud_rate = w_data["fraud_rate_pct"] / 100.0

    # We must use EXACTLY the feature columns defined in FEATURE_NAMES safely.
    X_train = df[df["split"] == "train"][FEATURE_NAMES].copy()
    y_train = df[df["split"] == "train"]["label"].values
    
    X_val = df[df["split"] == "val"][FEATURE_NAMES].copy()
    y_val = df[df["split"] == "val"]["label"].values
    
    X_test = df[df["split"] == "test"][FEATURE_NAMES].copy()
    y_test = df[df["split"] == "test"]["label"].values

    print(f"    Loaded in {time.time()-t0:.1f}s")
    print(f"    Train: {len(X_train):,} rows")
    print(f"    Val:   {len(X_val):,} rows")
    print(f"    Test:  {len(X_test):,} rows")
    print(f"    scale_pos_weight: {scale_pos_weight}")
    
    return (X_train, y_train, X_val, y_val, X_test, y_test), scale_pos_weight, fraud_rate


# ─────────────────────────────────────────────
# PHASE 2: XGBOOST (SUPERVISED)
# ─────────────────────────────────────────────

def train_xgboost(X_train: pd.DataFrame, y_train: np.ndarray, X_val: pd.DataFrame, y_val: np.ndarray, scale_pos_weight: float) -> xgb.XGBClassifier:
    print("\n[S5] Training XGBoost ...")
    
    # 1. Stratified subsample for Optuna
    if OPTUNA_SAMPLE_FRAC < 1.0:
        X_opt, _, y_opt, _ = train_test_split(
            X_train, y_train, 
            train_size=OPTUNA_SAMPLE_FRAC, 
            stratify=y_train, 
            random_state=42
        )
        print(f"    Optuna using {OPTUNA_SAMPLE_FRAC*100:.0f}% sample: {len(X_opt):,} rows")
    else:
        X_opt, y_opt = X_train, y_train
        
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "scale_pos_weight": scale_pos_weight,
            "tree_method": "hist",     # Fast histogram method
            "n_jobs": -1,              # Use all cores
            "random_state": 42
        }
        
        # Fast evaluation using early stopping on logic validation set
        model = xgb.XGBClassifier(**params)
        # Using a small internal split for Optuna scoring to avoid overfitting to the main validation set
        X_t_in, X_v_in, y_t_in, y_v_in = train_test_split(X_opt, y_opt, test_size=0.2, stratify=y_opt, random_state=42)
        
        model.fit(X_t_in, y_t_in, eval_set=[(X_v_in, y_v_in)], verbose=False)
        preds = model.predict_proba(X_v_in)[:, 1]
        
        # Optimize for AUCPR (Area Under Precision-Recall Curve) instead of ROC AUC
        return average_precision_score(y_v_in, preds)

    # Note: Optuna verbosity off to keep logs clean
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    print(f"    Running {OPTUNA_N_TRIALS} Optuna trials ... (this may take a few minutes)")
    t0 = time.time()
    study.optimize(objective, n_trials=OPTUNA_N_TRIALS, n_jobs=-1)
    
    best_params = study.best_params
    best_params["scale_pos_weight"] = scale_pos_weight
    best_params["tree_method"] = "hist"
    best_params["n_jobs"] = -1
    best_params["random_state"] = 42
    
    print(f"    Best params found in {time.time()-t0:.1f}s")
    for k, v in best_params.items():
        print(f"      {k}: {v}")
    
    print(f"    Refitting XGBoost on full Train data ({len(X_train):,} rows) ...")
    t1 = time.time()
    xgb_full = xgb.XGBClassifier(**best_params)
    # Fit the final model, using the main val set for early stopping as a safeguard
    xgb_full.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print(f"    Refit complete in {time.time()-t1:.1f}s")
    
    mlflow.log_params({f"xgb_{k}": v for k, v in best_params.items()})
    return xgb_full


# ─────────────────────────────────────────────
# PHASE 3: ISOLATION FOREST (UNSUPERVISED)
# ─────────────────────────────────────────────

def train_isoforest(X_train: pd.DataFrame, X_val: pd.DataFrame, fraud_rate: float):
    print("\n[S5] Training Isolation Forest ...")
    t0 = time.time()
    
    # Set contamination fraction to exactly the observed fraud rate + small buffer
    contamination = min(0.5, max(0.001, fraud_rate * 1.5))
    
    iso = IsolationForest(
        n_estimators=100, 
        contamination=contamination, 
        n_jobs=-1, 
        random_state=42
    )
    iso.fit(X_train)
    print(f"    Trained in {time.time()-t0:.1f}s (contamination={contamination:.4f})")
    mlflow.log_param("iso_contamination", contamination)
    
    # We need to normalize anomaly scores to [0, 100] for the ensemble
    # Isoforest decision_function yields lower (negative) values for anomalies.
    # So we want to invert it: Anomaly Score = - decision_function
    # Higher value = more anomalous.
    print("    Fitting IsoForest MinMaxScaler on validation set ...")
    val_scores_raw = -iso.decision_function(X_val)
    iso_scaler = MinMaxScaler(feature_range=(0, 100))
    iso_scaler.fit(val_scores_raw.reshape(-1, 1))
    
    return iso, iso_scaler


# ─────────────────────────────────────────────
# PHASE 4: AUTOENCODER (UNSUPERVISED)
# ─────────────────────────────────────────────

def train_autoencoder(X_train: pd.DataFrame, y_train: np.ndarray, X_val: pd.DataFrame):
    print(f"\n[S5] Training PyTorch Autoencoder on {DEVICE} ...")
    t0 = time.time()
    
    # NNs require scaled input data. 
    # Fit StandardScaler ONLY on the legitimate training transactions.
    X_train_legit = X_train[y_train == 0]
    
    ae_input_scaler = StandardScaler()
    X_train_legit_scaled = ae_input_scaler.fit_transform(X_train_legit)
    
    # DataLoaders
    tensor_x = torch.tensor(X_train_legit_scaled, dtype=torch.float32)
    dataset = TensorDataset(tensor_x)
    loader = DataLoader(dataset, batch_size=1024, shuffle=True)
    
    input_dim = X_train.shape[1]
    ae_model = FraudAutoencoder(input_dim).to(DEVICE)
    
    criterion = nn.MSELoss()
    optimizer = optim.Adam(ae_model.parameters(), lr=1e-3)
    
    # Keep it simple: 5 epochs is generally enough for this architecture on tabular data
    epochs = 5
    for epoch in range(epochs):
        ae_model.train()
        total_loss = 0.0
        for batch in loader:
            batch_x = batch[0].to(DEVICE)
            optimizer.zero_grad()
            reconstructed = ae_model(batch_x)
            loss = criterion(reconstructed, batch_x)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch_x.size(0)
            
        avg_loss = total_loss / len(tensor_x)
        print(f"    Epoch {epoch+1}/{epochs} - loss: {avg_loss:.4f}")
        
    print(f"    Trained in {time.time()-t0:.1f}s")
    
    # Normalize reconstruction errors (MSE per row) to 0-100 score
    print("    Fitting Autoencoder MinMaxScaler on validation set ...")
    ae_model.eval()
    X_val_scaled = ae_input_scaler.transform(X_val)
    
    val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32).to(DEVICE)
    with torch.no_grad():
        val_reconstructed = ae_model(val_tensor)
        # MSE per row
        val_mse = torch.mean((val_tensor - val_reconstructed)**2, dim=1).cpu().numpy()
        
    ae_scaler = MinMaxScaler(feature_range=(0, 100))
    ae_scaler.fit(val_mse.reshape(-1, 1))
    
    return ae_model, ae_input_scaler, ae_scaler


# ─────────────────────────────────────────────
# PHASE 5: EVALUATION & ENSEMBLE
# ─────────────────────────────────────────────

def compute_ensemble_scores(X: pd.DataFrame, models: dict) -> np.ndarray:
    """Computes the final ensemble score [0, 100] for a feature matrix"""
    xgb_model   = models["xgb"]
    iso_model   = models["iso"]
    iso_scaler  = models["iso_scaler"]
    ae_model    = models["ae"]
    ae_scaler   = models["ae_scaler"]
    ae_in_scale = models["ae_input_scaler"]
    
    # 1. XGBoost (0-100)
    xgb_proba = xgb_model.predict_proba(X)[:, 1]
    xgb_score = xgb_proba * 100.0
    
    # 2. IsoForest (0-100 inverted)
    iso_raw = -iso_model.decision_function(X)
    iso_score = iso_scaler.transform(iso_raw.reshape(-1, 1)).flatten()
    
    # 3. Autoencoder (0-100 MSE)
    X_scaled = ae_in_scale.transform(X)
    tens = torch.tensor(X_scaled, dtype=torch.float32).to(DEVICE)
    with torch.no_grad():
        ae_model.eval()
        recon = ae_model(tens)
        mse = torch.mean((tens - recon)**2, dim=1).cpu().numpy()
    ae_score = ae_scaler.transform(mse.reshape(-1, 1)).flatten()
    
    # 4. Ensemble
    final_score = (W_XGB * xgb_score) + (W_ISO * iso_score) + (W_AE * ae_score)
    
    # Clamp to [0, 100]
    return np.clip(final_score, 0, 100.0)


def evaluate_models(X_test: pd.DataFrame, y_test: np.ndarray, models: dict):
    print("\n[S5] Evaluating on Time-Ordered Test Set ...")
    
    scores = compute_ensemble_scores(X_test, models)
    
    # Compute threshold for Hard Rules / Block
    # We'll evaluate at threshold = 85.0
    THRESHOLD = 85.0
    y_pred = (scores >= THRESHOLD).astype(int)
    
    aucpr     = average_precision_score(y_test, scores)
    roc_auc   = roc_auc_score(y_test, scores)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    f1        = f1_score(y_test, y_pred, zero_division=0)
    
    print(f"    Test AUCPR:     {aucpr:.4f}")
    print(f"    Test ROC AUC:   {roc_auc:.4f}")
    print(f"    Test Precision: {precision:.4f} (at score >= {THRESHOLD})")
    print(f"    Test Recall:    {recall:.4f} (at score >= {THRESHOLD})")
    print(f"    Test F1 Score:  {f1:.4f}")
    
    mlflow.log_metrics({
        "test_aucpr": aucpr,
        "test_roc_auc": roc_auc,
        "test_precision": precision,
        "test_recall": recall,
        "test_f1": f1
    })


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("NeuralNexus_Fraud")
    
    print("\nStarting MLflow Run 'v1.0.0' ...")
    with mlflow.start_run(run_name="v1.0.0"):
        
        # 1. Data
        (X_tr, y_tr, X_v, y_v, X_te, y_te), spw, fr = load_data()
        mlflow.log_param("training_rows", len(X_tr))
        
        # 2. Train XGBoost
        xgb_model = train_xgboost(X_tr, y_tr, X_v, y_v, spw)
        joblib.dump(xgb_model, XGB_PATH)
        print(f"    ✓ Saved XGBoost to {XGB_PATH}")
        mlflow.log_artifact(XGB_PATH)
        
        # 3. Train IsoForest
        idx_sub = np.random.choice(len(X_tr), min(len(X_tr), max(100000, len(X_tr)//4)), replace=False) # fast fit
        iso_model, iso_scale = train_isoforest(X_tr.iloc[idx_sub], X_v, fr)
        joblib.dump(iso_model, ISO_PATH)
        print(f"    ✓ Saved IsoForest to {ISO_PATH}")
        mlflow.log_artifact(ISO_PATH)
        
        # 4. Train Autoencoder
        ae_model, ae_in_scale, ae_scale = train_autoencoder(X_tr, y_tr, X_v)
        torch.save(ae_model.state_dict(), AE_PATH)
        print(f"    ✓ Saved PyTorch Autoencoder to {AE_PATH}")
        mlflow.log_artifact(AE_PATH)
        
        # 5. Save all Scalers into a single dict artifact
        scalers_dict = {
            "iso_scaler": iso_scale,
            "ae_input_scaler": ae_in_scale,
            "ae_scaler": ae_scale
        }
        joblib.dump(scalers_dict, SCALER_PATH)
        print(f"    ✓ Saved Ensemble Scalers to {SCALER_PATH}")
        mlflow.log_artifact(SCALER_PATH)
        
        # 6. Precompute SHAP TreeExplainer
        print("\n[S5] Pre-computing SHAP TreeExplainer ...")
        t0 = time.time()
        explainer = shap.TreeExplainer(xgb_model)
        joblib.dump(explainer, SHAP_PATH)
        print(f"    ✓ Saved SHAP Explainer to {SHAP_PATH} (in {time.time()-t0:.1f}s)")
        mlflow.log_artifact(SHAP_PATH)
        
        # 7. Evaluate
        models_dict = {
            "xgb": xgb_model,
            "iso": iso_model,
            "iso_scaler": iso_scale,
            "ae": ae_model,
            "ae_scaler": ae_scale,
            "ae_input_scaler": ae_in_scale
        }
        evaluate_models(X_te, y_te, models_dict)
        
    print("\n✅ Stage S5 Complete! Models are ready for inference.")
    print("Next mapping → Stage S8 (FastAPI Prediction Engine)")

if __name__ == "__main__":
    main()
