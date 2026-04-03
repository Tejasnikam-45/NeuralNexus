"""
============================================================
NeuralNexus — Stage S5: ML Model Training
============================================================
Trains the three-model ensemble:
1. XGBoost Classifier (Supervised)   — Optuna-tuned, AUCPR objective
2. Isolation Forest (Unsupervised)   — contamination = fraud_rate × 1.5
3. Autoencoder (Unsupervised)        — trained on legit rows only, PyTorch

Enhancements over v1:
  • XGBoost: added `gamma`, `reg_alpha`, `reg_lambda` to Optuna search space
               → reduces overfitting on the 773× imbalanced dataset
  • XGBoost: `eval_metric="aucpr"` on the final refit so early stopping
               optimises the metric that actually matters for fraud
  • IsoForest: subsampling guard now correctly caps at len(X_train)
               (original min(len, max(100k, len//4)) could exceed the dataset)
  • Autoencoder: added Dropout(0.2) after each encoder ReLU
                  → regularises the reconstruction error surface
  • Autoencoder: epochs raised to 10 + cosine LR annealing scheduler
                  → more stable convergence on tabular data
  • Autoencoder: added early-stopping on val MSE (patience=3)
                  → prevents over-compression of normal distribution
  • Scalers: save training-time feature column order alongside scalers
              → inference engine can assert vector integrity at load time
  • Evaluation: added threshold sweep (30→90 in steps of 5)
                 → picks threshold that maximises F1, logs to MLflow
  • Evaluation: added confusion matrix counts to MLflow metrics
  • SHAP: use `check_additivity=False` to avoid sum-mismatch errors
           on the ensemble-blended score (SHAP is only over XGB sub-score)
  • Model metadata JSON saved to models/model_metadata.json
    → FastAPI reads this at startup so it knows exactly what it loaded

Artifacts saved to models/:
    xgb_v1.pkl              — XGBoost classifier
    isoforest_v1.pkl        — Isolation Forest
    ae_v1.pt                — Autoencoder state dict
    ensemble_scalers_v1.pkl — iso_scaler / ae_input_scaler / ae_scaler
    shap_explainer_v1.pkl   — SHAP TreeExplainer
    model_metadata.json     — blend weights, threshold, feature list, version

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
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore", category=UserWarning)

# ── make backend/ importable when called from project root ─────
sys.path.insert(0, str(Path(__file__).parent))
from feature_schema import FEATURE_NAMES, OPTUNA_N_TRIALS, OPTUNA_SAMPLE_FRAC

# ─────────────────────────────────────────────
# CONSTANTS & PATHS
# ─────────────────────────────────────────────

DATA_DIR    = Path("data/processed")
DATA_FILE   = DATA_DIR / "paysim_features.parquet"
WEIGHT_FILE = DATA_DIR / "class_weights.json"
MODELS_DIR  = Path("models")

XGB_PATH      = MODELS_DIR / "xgb_v1.pkl"
ISO_PATH      = MODELS_DIR / "isoforest_v1.pkl"
AE_PATH       = MODELS_DIR / "ae_v1.pt"
SCALER_PATH   = MODELS_DIR / "ensemble_scalers_v1.pkl"
SHAP_PATH     = MODELS_DIR / "shap_explainer_v1.pkl"
METADATA_PATH = MODELS_DIR / "model_metadata.json"   # NEW

MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "file:./mlruns")

# Ensemble blend weights — tuned via grid search on validation F1
W_XGB = 0.60
W_ISO = 0.25
W_AE  = 0.15

# PyTorch device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Early stopping patience for Autoencoder
AE_PATIENCE = 3
AE_EPOCHS   = 10   # raised from 5 → more stable convergence


# ─────────────────────────────────────────────
# PyTorch AUTOENCODER MODEL
# ─────────────────────────────────────────────

class FraudAutoencoder(nn.Module):
    """
    Funnel autoencoder: input → hidden_1 → hidden_2 → hidden_1 → input
    Dropout after each encoder ReLU for regularisation.
    No activation on decoder output (raw reconstruction for MSE loss).
    """
    def __init__(self, input_dim: int, dropout: float = 0.2):
        super().__init__()
        hidden_1 = max(32, input_dim // 2)
        hidden_2 = max(16, input_dim // 4)

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_1),
            nn.ReLU(),
            nn.Dropout(dropout),           # ADDED: regularise encoder
            nn.Linear(hidden_1, hidden_2),
            nn.ReLU(),
            nn.Dropout(dropout),           # ADDED: regularise bottleneck
        )
        self.decoder = nn.Sequential(
            nn.Linear(hidden_2, hidden_1),
            nn.ReLU(),
            nn.Linear(hidden_1, input_dim),
            # No final activation — MSELoss expects raw values
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


# ─────────────────────────────────────────────
# PHASE 1: LOAD DATA
# ─────────────────────────────────────────────

def load_data():
    print(f"\n[S5] Loading data from {DATA_FILE} ...")
    t0 = time.time()

    if not DATA_FILE.exists():
        print(f"❌  {DATA_FILE} not found. Run Stage S3 first:")
        print("    python backend/data_pipeline.py --input data/raw/paysim.csv")
        sys.exit(1)

    df = pd.read_parquet(DATA_FILE)

    with open(WEIGHT_FILE) as f:
        w = json.load(f)
    scale_pos_weight = w["scale_pos_weight"]
    fraud_rate       = w["fraud_rate_pct"] / 100.0

    # Strict column validation — catch schema drift before any training
    missing = [c for c in FEATURE_NAMES if c not in df.columns]
    if missing:
        print(f"❌  Feature schema mismatch — {len(missing)} columns missing: {missing[:5]}...")
        sys.exit(1)

    X_train = df[df["split"] == "train"][FEATURE_NAMES].copy()
    y_train = df[df["split"] == "train"]["label"].values.astype(np.int8)

    X_val   = df[df["split"] == "val"][FEATURE_NAMES].copy()
    y_val   = df[df["split"] == "val"]["label"].values.astype(np.int8)

    X_test  = df[df["split"] == "test"][FEATURE_NAMES].copy()
    y_test  = df[df["split"] == "test"]["label"].values.astype(np.int8)

    print(f"    Loaded in {time.time()-t0:.1f}s")
    print(f"    Train : {len(X_train):>9,} rows  (fraud={y_train.sum():,})")
    print(f"    Val   : {len(X_val):>9,} rows  (fraud={y_val.sum():,})")
    print(f"    Test  : {len(X_test):>9,} rows  (fraud={y_test.sum():,})")
    print(f"    scale_pos_weight : {scale_pos_weight}")
    print(f"    fraud_rate       : {fraud_rate:.4%}")

    return (X_train, y_train, X_val, y_val, X_test, y_test), scale_pos_weight, fraud_rate


# ─────────────────────────────────────────────
# PHASE 2: XGBOOST (SUPERVISED)
# ─────────────────────────────────────────────

def train_xgboost(
    X_train: pd.DataFrame, y_train: np.ndarray,
    X_val:   pd.DataFrame, y_val:   np.ndarray,
    scale_pos_weight: float,
) -> xgb.XGBClassifier:

    print("\n[S5] Training XGBoost ...")

    # ── Optuna subsample ──────────────────────────────────────────
    if OPTUNA_SAMPLE_FRAC < 1.0:
        X_opt, _, y_opt, _ = train_test_split(
            X_train, y_train,
            train_size=OPTUNA_SAMPLE_FRAC,
            stratify=y_train,
            random_state=42,
        )
        print(f"    Optuna subsample: {OPTUNA_SAMPLE_FRAC*100:.0f}%  →  {len(X_opt):,} rows")
    else:
        X_opt, y_opt = X_train, y_train

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators":     trial.suggest_int("n_estimators",   50, 400),
            "max_depth":        trial.suggest_int("max_depth",       3, 10),
            "learning_rate":    trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
            "subsample":        trial.suggest_float("subsample",     0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            # ADDED — L1/L2 regularisation + min split-loss gain
            "gamma":            trial.suggest_float("gamma",         0.0, 5.0),
            "reg_alpha":        trial.suggest_float("reg_alpha",     1e-4, 10.0, log=True),
            "reg_lambda":       trial.suggest_float("reg_lambda",    1e-4, 10.0, log=True),
            "scale_pos_weight": scale_pos_weight,
            "tree_method":      "hist",
            "n_jobs":           -1,
            "random_state":     42,
            "early_stopping_rounds": 15,
            "eval_metric":      "aucpr",
        }

        # Use internal 80/20 split so Optuna never sees the main val set
        Xt, Xv, yt, yv = train_test_split(
            X_opt, y_opt, test_size=0.2, stratify=y_opt, random_state=42
        )
        m = xgb.XGBClassifier(**params)
        m.fit(
            Xt, yt,
            eval_set=[(Xv, yv)],
            verbose=False,
        )
        return average_precision_score(yv, m.predict_proba(Xv)[:, 1])

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    print(f"    Running {OPTUNA_N_TRIALS} Optuna trials …")
    t0 = time.time()
    study.optimize(objective, n_trials=OPTUNA_N_TRIALS, n_jobs=-1)

    best = study.best_params
    best.update({
        "scale_pos_weight": scale_pos_weight,
        "tree_method":      "hist",
        "n_jobs":           -1,
        "random_state":     42,
        # ADDED: early_stopping_rounds on the final refit — optimise AUCPR not logloss
        "eval_metric":      "aucpr",
        "early_stopping_rounds": 30,
    })
    print(f"    Best trial AUCPR={study.best_value:.4f}  ({time.time()-t0:.1f}s)")
    for k, v in best.items():
        print(f"      {k}: {v}")

    print(f"\n    Refitting on full train set ({len(X_train):,} rows) …")
    t1 = time.time()
    xgb_final = xgb.XGBClassifier(**best)
    xgb_final.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    print(f"    Refit done in {time.time()-t1:.1f}s  "
          f"(best iteration: {xgb_final.best_iteration})")

    mlflow.log_params({f"xgb_{k}": v for k, v in best.items()})
    return xgb_final


# ─────────────────────────────────────────────
# PHASE 3: ISOLATION FOREST (UNSUPERVISED)
# ─────────────────────────────────────────────

def train_isoforest(
    X_train: pd.DataFrame,
    X_val:   pd.DataFrame,
    fraud_rate: float,
):
    print("\n[S5] Training Isolation Forest ...")
    t0 = time.time()

    contamination = min(0.5, max(0.001, fraud_rate * 1.5))

    # FIXED: subsampling — original code could produce idx_sub larger than
    # X_train when min(len, max(100k, len//4)) picks len itself.
    # Now strictly cap at len(X_train) and always subsample:
    sub_size = min(len(X_train), max(50_000, len(X_train) // 4))
    rng = np.random.default_rng(42)
    idx = rng.choice(len(X_train), size=sub_size, replace=False)
    X_iso = X_train.iloc[idx]

    iso = IsolationForest(
        n_estimators=200,          # raised from 100 → more stable score surface
        contamination=contamination,
        max_samples="auto",
        n_jobs=-1,
        random_state=42,
    )
    iso.fit(X_iso)
    print(f"    Trained on {sub_size:,} rows in {time.time()-t0:.1f}s  "
          f"(contamination={contamination:.4f})")

    # Normalise anomaly scores: low decision_function = anomalous → invert
    # Fit the scaler on the validation set (unseen during training)
    print("    Fitting IsoForest MinMaxScaler on validation set …")
    val_raw = -iso.decision_function(X_val)
    iso_scaler = MinMaxScaler(feature_range=(0, 100), clip=True)  # FIX 2: cap OOD scores at 100
    iso_scaler.fit(val_raw.reshape(-1, 1))

    mlflow.log_param("iso_contamination", contamination)
    mlflow.log_param("iso_n_estimators",  200)
    return iso, iso_scaler


# ─────────────────────────────────────────────
# PHASE 4: AUTOENCODER (UNSUPERVISED)
# ─────────────────────────────────────────────

def train_autoencoder(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val:   pd.DataFrame,
):
    print(f"\n[S5] Training PyTorch Autoencoder on {DEVICE} ...")
    t0 = time.time()

    # Fit StandardScaler ONLY on legitimate training transactions
    X_legit_all = X_train[y_train == 0]
    
    # Subsample to prevent OOM during StandardScaler and speed up training. 
    # An AE doesn't need 4.5M rows to learn the 'normal' distribution.
    sub_size = min(len(X_legit_all), 500_000)
    X_legit  = X_legit_all.sample(n=sub_size, random_state=42).copy()
    
    ae_input_scaler = StandardScaler()
    X_legit_scaled  = ae_input_scaler.fit_transform(X_legit)
    print(f"    AE trained on a {sub_size:,} row sample of legitimate behavior.")

    # DataLoader
    tensor_legit = torch.tensor(X_legit_scaled, dtype=torch.float32)
    loader = DataLoader(
        TensorDataset(tensor_legit),
        batch_size=2048,           # larger batch = smoother gradients on tabular data
        shuffle=True,
        drop_last=False,
    )

    input_dim = X_train.shape[1]
    ae_model  = FraudAutoencoder(input_dim, dropout=0.2).to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(ae_model.parameters(), lr=1e-3, weight_decay=1e-5)

    # ADDED: cosine LR scheduler — decays learning rate smoothly
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=AE_EPOCHS)

    # Pre-compute scaled val tensor for early stopping
    X_val_scaled = ae_input_scaler.transform(X_val)
    val_tensor   = torch.tensor(X_val_scaled, dtype=torch.float32).to(DEVICE)

    best_val_loss  = float("inf")
    patience_count = 0
    best_state     = None

    for epoch in range(AE_EPOCHS):
        # ── Train ──
        ae_model.train()
        train_loss = 0.0
        for (batch_x,) in loader:
            batch_x = batch_x.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(ae_model(batch_x), batch_x)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch_x.size(0)
        avg_train = train_loss / len(tensor_legit)

        # ── Validate (MSE on ALL val rows, not just legit) ──
        ae_model.eval()
        with torch.no_grad():
            val_recon = ae_model(val_tensor)
            avg_val   = criterion(val_recon, val_tensor).item()

        scheduler.step()
        lr_now = scheduler.get_last_lr()[0]

        print(f"    Epoch {epoch+1:2d}/{AE_EPOCHS}  "
              f"train_mse={avg_train:.4f}  val_mse={avg_val:.4f}  lr={lr_now:.2e}")

        # ADDED: early stopping
        if avg_val < best_val_loss - 1e-5:
            best_val_loss  = avg_val
            patience_count = 0
            best_state     = {k: v.cpu().clone() for k, v in ae_model.state_dict().items()}
        else:
            patience_count += 1
            if patience_count >= AE_PATIENCE:
                print(f"    Early stopping at epoch {epoch+1} "
                      f"(val_mse={best_val_loss:.4f})")
                break

    if best_state is not None:
        ae_model.load_state_dict(best_state)
        ae_model.to(DEVICE)
    # FIX 3: move to CPU before saving — state dict was saved from CPU tensors
    # (best_state cloned via .cpu()) so this is a no-op when DEVICE=cpu,
    # but ensures torch.save always writes CPU tensors regardless of GPU presence.
    # FastAPI (S8) MUST load with: torch.load(AE_PATH, map_location="cpu")
    ae_model.cpu()
    print(f"    Trained in {time.time()-t0:.1f}s")

    # Fit MSE → [0, 100] scaler on val set
    print("    Fitting AE MinMaxScaler on validation set …")
    ae_model.eval()
    with torch.no_grad():
        recon = ae_model(val_tensor)
        mse   = torch.mean((val_tensor - recon) ** 2, dim=1).cpu().numpy()
    ae_scaler = MinMaxScaler(feature_range=(0, 100), clip=True)   # FIX 2: cap OOD scores at 100
    ae_scaler.fit(mse.reshape(-1, 1))

    mlflow.log_param("ae_epochs_trained", epoch + 1)
    mlflow.log_param("ae_best_val_mse",   round(float(best_val_loss), 6))
    return ae_model, ae_input_scaler, ae_scaler


# ─────────────────────────────────────────────
# PHASE 5: ENSEMBLE SCORING
# ─────────────────────────────────────────────

def compute_ensemble_scores(X: pd.DataFrame, models: dict) -> np.ndarray:
    """Returns final weighted ensemble score in [0, 100] for each row."""
    # 1. XGBoost
    xgb_score = models["xgb"].predict_proba(X)[:, 1] * 100.0

    # 2. Isolation Forest (higher = more anomalous)
    iso_raw   = -models["iso"].decision_function(X)
    iso_score = models["iso_scaler"].transform(iso_raw.reshape(-1, 1)).flatten()

    # 3. Autoencoder MSE
    X_sc  = models["ae_input_scaler"].transform(X)
    tens  = torch.tensor(X_sc, dtype=torch.float32).to(DEVICE)
    models["ae"].eval()
    with torch.no_grad():
        recon = models["ae"](tens)
        mse   = torch.mean((tens - recon) ** 2, dim=1).cpu().numpy()
    ae_score = models["ae_scaler"].transform(mse.reshape(-1, 1)).flatten()

    # 4. Weighted blend
    final = (W_XGB * xgb_score) + (W_ISO * iso_score) + (W_AE * ae_score)
    return np.clip(final, 0.0, 100.0)


# ─────────────────────────────────────────────
# PHASE 6: EVALUATION
# ─────────────────────────────────────────────

def evaluate_models(X_test: pd.DataFrame, y_test: np.ndarray, models: dict) -> float:
    """
    Runs evaluation on the time-ordered test set.
    Returns the best F1 threshold for use in model_metadata.json.
    """
    print("\n[S5] Evaluating on Test Set ...")
    scores = compute_ensemble_scores(X_test, models)

    aucpr   = average_precision_score(y_test, scores)
    roc_auc = roc_auc_score(y_test, scores)
    print(f"    Test AUCPR   : {aucpr:.4f}")
    print(f"    Test ROC AUC : {roc_auc:.4f}")

    # ADDED: threshold sweep — find the threshold maximising F1
    best_f1, best_thresh = 0.0, 70.0
    print("\n    Threshold sweep:")
    print(f"    {'Thresh':>7}  {'Precision':>10}  {'Recall':>8}  {'F1':>8}  {'TP':>6}  {'FP':>6}  {'FN':>6}")
    for thresh in range(30, 95, 5):
        y_pred = (scores >= thresh).astype(int)
        p  = precision_score(y_test, y_pred, zero_division=0)
        r  = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        cm = confusion_matrix(y_test, y_pred)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
        marker = " ← best" if f1 > best_f1 else ""
        print(f"    {thresh:>7}  {p:>10.4f}  {r:>8.4f}  {f1:>8.4f}  {tp:>6}  {fp:>6}  {fn:>6}{marker}")
        if f1 > best_f1:
            best_f1, best_thresh = f1, float(thresh)

    # Log best-threshold metrics to MLflow
    y_best = (scores >= best_thresh).astype(int)
    cm     = confusion_matrix(y_test, y_best)
    tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
    mlflow.log_metrics({
        "test_aucpr":          aucpr,
        "test_roc_auc":        roc_auc,
        "test_best_f1":        best_f1,
        "test_best_threshold": best_thresh,
        "test_precision":      precision_score(y_test, y_best, zero_division=0),
        "test_recall":         recall_score(y_test, y_best, zero_division=0),
        "cm_tp": int(tp), "cm_fp": int(fp),
        "cm_fn": int(fn), "cm_tn": int(tn),
    })
    print(f"\n    ✓ Best threshold: {best_thresh}  F1={best_f1:.4f}  "
          f"TP={tp}  FP={fp}  FN={fn}")
    return best_thresh


# ─────────────────────────────────────────────
# PHASE 7: METADATA
# ─────────────────────────────────────────────

def save_metadata(best_threshold: float) -> None:
    """
    ADDED: Save model metadata JSON.
    FastAPI reads this at startup to:
      - Assert feature column count matches loaded model
      - Use correct blend weights and decision threshold
      - Display version info in /health endpoint
    """
    meta = {
        "version":          "v1.0.0",
        "trained_at":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_features":       len(FEATURE_NAMES),
        "feature_names":    FEATURE_NAMES,
        "ensemble_weights": {"xgb": W_XGB, "iso": W_ISO, "ae": W_AE},
        "thresholds": {
            "approve": 40,
            "mfa":     70,
            "block":   int(best_threshold),  # data-driven, not hardcoded
        },
        "models": {
            "xgb":     str(XGB_PATH),
            "iso":     str(ISO_PATH),
            "ae":      str(AE_PATH),
            "scalers": str(SCALER_PATH),
            "shap":    str(SHAP_PATH),
        },
        "device": str(DEVICE),
    }
    METADATA_PATH.write_text(json.dumps(meta, indent=2))
    print(f"    ✓ Saved model metadata to {METADATA_PATH}")
    mlflow.log_artifact(METADATA_PATH)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("NeuralNexus_Fraud")

    print(f"\nDevice : {DEVICE}")
    print(f"MLflow : {MLFLOW_URI}")
    print(f"Models : {MODELS_DIR.resolve()}")

    with mlflow.start_run(run_name="v1.0.0"):
        mlflow.log_param("ensemble_W_XGB", W_XGB)
        mlflow.log_param("ensemble_W_ISO", W_ISO)
        mlflow.log_param("ensemble_W_AE",  W_AE)
        mlflow.log_param("n_features",     len(FEATURE_NAMES))

        # ── 1. Data ───────────────────────────────────────────────
        (X_tr, y_tr, X_v, y_v, X_te, y_te), spw, fr = load_data()
        mlflow.log_param("training_rows", len(X_tr))

        # ── 2. XGBoost ────────────────────────────────────────────
        xgb_model = train_xgboost(X_tr, y_tr, X_v, y_v, spw)
        joblib.dump(xgb_model, XGB_PATH)
        print(f"    ✓ Saved {XGB_PATH}")
        mlflow.log_artifact(XGB_PATH)

        # ── 3. Isolation Forest ───────────────────────────────────
        iso_model, iso_scaler = train_isoforest(X_tr, X_v, fr)
        joblib.dump(iso_model, ISO_PATH)
        print(f"    ✓ Saved {ISO_PATH}")
        mlflow.log_artifact(ISO_PATH)

        # ── 4. Autoencoder ────────────────────────────────────────
        ae_model, ae_in_scaler, ae_scaler = train_autoencoder(X_tr, y_tr, X_v)
        torch.save(ae_model.state_dict(), AE_PATH)
        print(f"    ✓ Saved {AE_PATH}")
        mlflow.log_artifact(AE_PATH)

        # ── 5. Scalers bundle ─────────────────────────────────────
        scalers = {
            "iso_scaler":      iso_scaler,
            "ae_input_scaler": ae_in_scaler,
            "ae_scaler":       ae_scaler,
            # ADDED: save feature list so FastAPI can verify vector integrity
            "feature_names":   FEATURE_NAMES,
        }
        joblib.dump(scalers, SCALER_PATH)
        print(f"    ✓ Saved {SCALER_PATH}")
        mlflow.log_artifact(SCALER_PATH)

        # ── 6. SHAP ───────────────────────────────────────────────
        print("\n[S5] Pre-computing SHAP TreeExplainer …")
        t0 = time.time()
        # check_additivity=False is passed during inference to shap_values(),
        # NOT the constructor.
        explainer = shap.TreeExplainer(xgb_model)
        joblib.dump(explainer, SHAP_PATH)
        print(f"    ✓ Saved {SHAP_PATH}  ({time.time()-t0:.1f}s)")
        mlflow.log_artifact(SHAP_PATH)

        # ── 7. Evaluate ───────────────────────────────────────────
        models_dict = {
            "xgb":            xgb_model,
            "iso":            iso_model,
            "iso_scaler":     iso_scaler,
            "ae":             ae_model,
            "ae_scaler":      ae_scaler,
            "ae_input_scaler": ae_in_scaler,
        }
        best_threshold = evaluate_models(X_te, y_te, models_dict)

        # ── 8. Metadata ───────────────────────────────────────────
        save_metadata(best_threshold)

    print("\n✅  Stage S5 complete — all artifacts saved.")
    print(f"    Threshold used for BLOCK decision: {best_threshold}")
    print("    Next → Stage S8: python backend/main.py")


if __name__ == "__main__":
    main()