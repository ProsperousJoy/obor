"""
Wildfire Sentinel — Multi-Model Training, Hyperparameter Exploration & Overfitting Benchmark
--------------------------------------------------------------------------------------------
Trains and benchmarks:
  1. LightGBM (Shallow, Balanced, Deep-Regularized)
  2. XGBoost (Shallow, Balanced, Deep-Regularized)
  3. CatBoost (Shallow, Balanced, Deep-Regularized)
  4. Random Forest (Shallow, Balanced, High-Trees)
  5. Neural Network / MLP (Shallow-Dropout, Deep-Regularized)
  6. Regularized Baseline (Logistic Regression / Ridge)

Evaluates:
  - Both Classification (target_has_fire_24h) and Regression (target_fire_intensity_24h)
  - Train vs Validation vs Out-of-Time Test (2021-2023 Train, 2024 Val, 2025 Test)
  - Strict Overfitting Tracking: Delta(PR-AUC) = Train - Val
  - Automated selection and serialization of the optimal models
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd
import joblib

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    balanced_accuracy_score,
    confusion_matrix,
    mean_squared_error,
    mean_absolute_error,
    r2_score
)
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wildfire_benchmark")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
from src.config import config
DB_PATH = Path(config.WAREHOUSE_DB_PATH)
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "models"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 16 Scientifically Valid Baseline Features (Non-Null, Antecedent)
FEATURE_COLS = [
    "prev_day_t2m_max_c",
    "prev_day_rh_min_pct",
    "prev_day_precip_mm",
    "prev_day_wind_speed_kmh",
    "prev_day_soil_moisture",
    "rain_accum_7d_mm",
    "rain_accum_30d_mm",
    "consecutive_dry_days",
    "t2m_anomaly_vs_30d_mean",
    "hotspot_count_prev_24h",
    "hotspot_count_prev_7d",
    "max_frp_prev_7d",
    "has_recent_fire_7d",
    "month",
    "centroid_lat",
    "centroid_lon",
]

TARGET_CLF = "target_has_fire_24h"
TARGET_REG = "target_fire_intensity_24h"


def load_dataset(db_path: Path):
    """Load train, val, and test splits from DuckDB vw_training_dataset."""
    logger.info(f"Connecting to DuckDB data warehouse at {db_path}...")
    con = duckdb.connect(str(db_path), read_only=True)
    
    query = f"""
        SELECT 
            sample_id, grid_id, target_datetime, split, year, month,
            {', '.join(FEATURE_COLS)},
            {TARGET_CLF}, {TARGET_REG}
        FROM vw_training_dataset
    """
    logger.info("Executing analytical query on vw_training_dataset...")
    start_t = time.time()
    df = con.execute(query).df()
    elapsed = time.time() - start_t
    con.close()
    
    logger.info(f"Loaded {len(df):,} samples with {df.shape[1]} columns in {elapsed:.2f}s.")
    
    # Preprocess boolean to int
    df["has_recent_fire_7d"] = df["has_recent_fire_7d"].astype(int)
    df[TARGET_CLF] = df[TARGET_CLF].astype(int)
    df[TARGET_REG] = df[TARGET_REG].fillna(0.0).astype(float)
    
    # Split into Train, Val, Test
    train_df = df[df["split"] == "TRAIN"].copy()
    val_df = df[df["split"] == "VAL"].copy()
    test_df = df[df["split"] == "TEST"].copy()
    
    logger.info(f"Split breakdown: Train={len(train_df):,} (2021-2023), Val={len(val_df):,} (2024), Test={len(test_df):,} (2025)")
    return train_df, val_df, test_df


def prepare_features(train_df, val_df, test_df):
    """Impute and standardize features."""
    imputer = SimpleImputer(strategy="median")
    
    X_train = imputer.fit_transform(train_df[FEATURE_COLS])
    X_val = imputer.transform(val_df[FEATURE_COLS])
    X_test = imputer.transform(test_df[FEATURE_COLS])
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    
    y_clf_train = train_df[TARGET_CLF].values
    y_clf_val = val_df[TARGET_CLF].values
    y_clf_test = test_df[TARGET_CLF].values
    
    y_reg_train = train_df[TARGET_REG].values
    y_reg_val = val_df[TARGET_REG].values
    y_reg_test = test_df[TARGET_REG].values
    
    return {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "X_train_scaled": X_train_scaled, "X_val_scaled": X_val_scaled, "X_test_scaled": X_test_scaled,
        "y_clf_train": y_clf_train, "y_clf_val": y_clf_val, "y_clf_test": y_clf_test,
        "y_reg_train": y_reg_train, "y_reg_val": y_reg_val, "y_reg_test": y_reg_test,
        "imputer": imputer, "scaler": scaler
    }


def evaluate_classifier(name, config_name, model, X_tr, y_tr, X_va, y_val, X_te, y_te, is_scaled=False):
    """Train classifier and evaluate on train, val, and test, tracking overfitting."""
    start_t = time.time()
    logger.info(f"--> Training Classifier: {name} [{config_name}]...")
    model.fit(X_tr, y_tr)
    fit_time = time.time() - start_t
    
    # Train metrics (for overfitting tracking)
    p_tr = model.predict_proba(X_tr)[:, 1]
    auc_tr = roc_auc_score(y_tr, p_tr)
    pr_auc_tr = average_precision_score(y_tr, p_tr)
    
    # Val metrics (for tuning & selection)
    p_va = model.predict_proba(X_va)[:, 1]
    auc_va = roc_auc_score(y_val, p_va)
    pr_auc_va = average_precision_score(y_val, p_va)
    brier_va = brier_score_loss(y_val, p_va)
    
    # Test metrics (out-of-time holdout)
    p_te = model.predict_proba(X_te)[:, 1]
    auc_te = roc_auc_score(y_te, p_te)
    pr_auc_te = average_precision_score(y_te, p_te)
    brier_te = brier_score_loss(y_te, p_te)
    
    # Overfitting gaps
    auc_gap = float(auc_tr - auc_va)
    pr_auc_gap = float(pr_auc_tr - pr_auc_va)
    is_overfitting = bool(pr_auc_gap > 0.05 or auc_gap > 0.05)
    
    # Optimal threshold based on Val F1
    best_th = 0.5
    best_f1 = 0.0
    for th in np.linspace(0.2, 0.8, 13):
        preds = (p_va >= th).astype(int)
        f = f1_score(y_val, preds, zero_division=0)
        if f > best_f1:
            best_f1 = f
            best_th = th
            
    val_preds = (p_va >= best_th).astype(int)
    bal_acc = balanced_accuracy_score(y_val, val_preds)
    cm = confusion_matrix(y_val, val_preds).tolist()
    
    res = {
        "model_family": name,
        "config_name": config_name,
        "fit_time_sec": round(fit_time, 2),
        "train": {
            "roc_auc": round(float(auc_tr), 4),
            "pr_auc": round(float(pr_auc_tr), 4)
        },
        "val": {
            "roc_auc": round(float(auc_va), 4),
            "pr_auc": round(float(pr_auc_va), 4),
            "brier_score": round(float(brier_va), 4),
            "f1_score": round(float(best_f1), 4),
            "optimal_threshold": round(float(best_th), 3),
            "balanced_accuracy": round(float(bal_acc), 4),
            "confusion_matrix": {"tn": cm[0][0], "fp": cm[0][1], "fn": cm[1][0], "tp": cm[1][1]}
        },
        "test": {
            "roc_auc": round(float(auc_te), 4),
            "pr_auc": round(float(pr_auc_te), 4),
            "brier_score": round(float(brier_te), 4)
        },
        "overfitting": {
            "roc_auc_gap": round(auc_gap, 4),
            "pr_auc_gap": round(pr_auc_gap, 4),
            "is_flagged_overfitting": is_overfitting
        }
    }
    logger.info(
        f"    Val PR-AUC: {pr_auc_va:.4f} | Val ROC-AUC: {auc_va:.4f} | "
        f"Gap: {pr_auc_gap:+.4f} ({'OVERFIT' if is_overfitting else 'STABLE'}) | Time: {fit_time:.1f}s"
    )
    return res, model


def evaluate_regressor(name, config_name, model, X_tr, y_tr, X_va, y_val, X_te, y_te):
    """Train regressor for fire intensity (FRP in MW) and evaluate on train, val, test."""
    start_t = time.time()
    logger.info(f"--> Training Regressor: {name} [{config_name}]...")
    model.fit(X_tr, y_tr)
    fit_time = time.time() - start_t
    
    # Train
    p_tr = np.clip(model.predict(X_tr), 0, None)
    rmse_tr = float(np.sqrt(mean_squared_error(y_tr, p_tr)))
    mae_tr = float(mean_absolute_error(y_tr, p_tr))
    
    # Val
    p_va = np.clip(model.predict(X_va), 0, None)
    rmse_va = float(np.sqrt(mean_squared_error(y_val, p_va)))
    mae_va = float(mean_absolute_error(y_val, p_va))
    r2_va = float(r2_score(y_val, p_va))
    
    # Test
    p_te = np.clip(model.predict(X_te), 0, None)
    rmse_te = float(np.sqrt(mean_squared_error(y_te, p_te)))
    mae_te = float(mean_absolute_error(y_te, p_te))
    r2_te = float(r2_score(y_te, p_te))
    
    rmse_gap = float(rmse_va - rmse_tr)
    
    res = {
        "model_family": name,
        "config_name": config_name,
        "fit_time_sec": round(fit_time, 2),
        "train": {"rmse": round(rmse_tr, 3), "mae": round(mae_tr, 3)},
        "val": {"rmse": round(rmse_va, 3), "mae": round(mae_va, 3), "r2": round(r2_va, 4)},
        "test": {"rmse": round(rmse_te, 3), "mae": round(mae_te, 3), "r2": round(r2_te, 4)},
        "overfitting": {"rmse_gap": round(rmse_gap, 3)}
    }
    logger.info(f"    Val RMSE: {rmse_va:.2f} MW | Val MAE: {mae_va:.2f} MW | R2: {r2_va:.4f} | Time: {fit_time:.1f}s")
    return res, model


def run_benchmark():
    train_df, val_df, test_df = load_dataset(DB_PATH)
    data = prepare_features(train_df, val_df, test_df)
    
    X_tr, X_va, X_te = data["X_train"], data["X_val"], data["X_test"]
    X_tr_sc, X_va_sc, X_te_sc = data["X_train_scaled"], data["X_val_scaled"], data["X_test_scaled"]
    y_clf_tr, y_clf_va, y_clf_te = data["y_clf_train"], data["y_clf_val"], data["y_clf_test"]
    y_reg_tr, y_reg_va, y_reg_te = data["y_reg_train"], data["y_reg_val"], data["y_reg_test"]
    
    clf_results = []
    trained_clf_models = {}
    
    reg_results = []
    trained_reg_models = {}
    
    # =========================================================================
    # 1. LIGHTGBM CLASSIFIERS & REGRESSORS
    # =========================================================================
    try:
        import lightgbm as lgb
        logger.info("\n=== BENCHMARKING LIGHTGBM ===")
        lgb_configs = [
            ("LGBM-Shallow", {"n_estimators": 100, "max_depth": 4, "num_leaves": 15, "learning_rate": 0.08, "class_weight": "balanced", "random_state": 42, "n_jobs": -1}),
            ("LGBM-Balanced", {"n_estimators": 150, "max_depth": 6, "num_leaves": 31, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0, "class_weight": "balanced", "random_state": 42, "n_jobs": -1}),
            ("LGBM-Deep-Regularized", {"n_estimators": 200, "max_depth": 8, "num_leaves": 63, "learning_rate": 0.03, "subsample": 0.7, "colsample_bytree": 0.7, "reg_alpha": 1.0, "reg_lambda": 5.0, "min_child_samples": 50, "class_weight": "balanced", "random_state": 42, "n_jobs": -1})
        ]
        for cfg_name, params in lgb_configs:
            model = lgb.LGBMClassifier(**params)
            res, trained = evaluate_classifier("LightGBM", cfg_name, model, X_tr, y_clf_tr, X_va, y_clf_va, X_te, y_clf_te)
            clf_results.append(res)
            trained_clf_models[f"LightGBM_{cfg_name}"] = trained
            
            # Regression variant
            reg_params = {k: v for k, v in params.items() if k != "class_weight"}
            reg_model = lgb.LGBMRegressor(**reg_params)
            r_res, r_trained = evaluate_regressor("LightGBM", cfg_name, reg_model, X_tr, y_reg_tr, X_va, y_reg_va, X_te, y_reg_te)
            reg_results.append(r_res)
            trained_reg_models[f"LightGBM_{cfg_name}"] = r_trained
    except ImportError:
        logger.warning("LightGBM is not installed.")

    # =========================================================================
    # 2. XGBOOST CLASSIFIERS & REGRESSORS
    # =========================================================================
    try:
        import xgboost as xgb
        logger.info("\n=== BENCHMARKING XGBOOST ===")
        # Calculate scale_pos_weight for imbalance
        scale_pos = float((len(y_clf_tr) - sum(y_clf_tr)) / sum(y_clf_tr))
        xgb_configs = [
            ("XGB-Shallow", {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.08, "scale_pos_weight": scale_pos, "random_state": 42, "n_jobs": -1, "tree_method": "hist"}),
            ("XGB-Balanced", {"n_estimators": 150, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0, "scale_pos_weight": scale_pos, "random_state": 42, "n_jobs": -1, "tree_method": "hist"}),
            ("XGB-Deep-Regularized", {"n_estimators": 200, "max_depth": 8, "learning_rate": 0.03, "subsample": 0.7, "colsample_bytree": 0.7, "reg_alpha": 1.0, "reg_lambda": 5.0, "scale_pos_weight": scale_pos, "random_state": 42, "n_jobs": -1, "tree_method": "hist"})
        ]
        for cfg_name, params in xgb_configs:
            model = xgb.XGBClassifier(**params)
            res, trained = evaluate_classifier("XGBoost", cfg_name, model, X_tr, y_clf_tr, X_va, y_clf_va, X_te, y_clf_te)
            clf_results.append(res)
            trained_clf_models[f"XGBoost_{cfg_name}"] = trained
            
            # Regression variant
            reg_params = {k: v for k, v in params.items() if k != "scale_pos_weight"}
            reg_model = xgb.XGBRegressor(**reg_params)
            r_res, r_trained = evaluate_regressor("XGBoost", cfg_name, reg_model, X_tr, y_reg_tr, X_va, y_reg_va, X_te, y_reg_te)
            reg_results.append(r_res)
            trained_reg_models[f"XGBoost_{cfg_name}"] = r_trained
    except ImportError:
        logger.warning("XGBoost is not installed.")

    # =========================================================================
    # 3. CATBOOST CLASSIFIERS & REGRESSORS
    # =========================================================================
    try:
        import catboost as cb
        logger.info("\n=== BENCHMARKING CATBOOST ===")
        cb_configs = [
            ("CatBoost-Shallow", {"iterations": 120, "depth": 4, "learning_rate": 0.08, "auto_class_weights": "Balanced", "verbose": 0, "random_seed": 42, "thread_count": -1}),
            ("CatBoost-Balanced", {"iterations": 150, "depth": 6, "learning_rate": 0.05, "l2_leaf_reg": 3.0, "auto_class_weights": "Balanced", "verbose": 0, "random_seed": 42, "thread_count": -1}),
            ("CatBoost-Deep-Regularized", {"iterations": 200, "depth": 7, "learning_rate": 0.03, "l2_leaf_reg": 8.0, "auto_class_weights": "Balanced", "verbose": 0, "random_seed": 42, "thread_count": -1})
        ]
        for cfg_name, params in cb_configs:
            model = cb.CatBoostClassifier(**params)
            res, trained = evaluate_classifier("CatBoost", cfg_name, model, X_tr, y_clf_tr, X_va, y_clf_va, X_te, y_clf_te)
            clf_results.append(res)
            trained_clf_models[f"CatBoost_{cfg_name}"] = trained
            
            # Regression variant
            reg_params = {k: v for k, v in params.items() if k != "auto_class_weights"}
            reg_model = cb.CatBoostRegressor(**reg_params)
            r_res, r_trained = evaluate_regressor("CatBoost", cfg_name, reg_model, X_tr, y_reg_tr, X_va, y_reg_va, X_te, y_reg_te)
            reg_results.append(r_res)
            trained_reg_models[f"CatBoost_{cfg_name}"] = r_trained
    except ImportError:
        logger.warning("CatBoost is not installed.")

    # =========================================================================
    # 4. HIST GRADIENT BOOSTING (Native Scikit-Learn Fast Tree Booster)
    # =========================================================================
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    logger.info("\n=== BENCHMARKING HIST GRADIENT BOOSTING ===")
    hgb_configs = [
        ("HGB-Shallow", {"max_iter": 80, "max_depth": 5, "learning_rate": 0.08, "class_weight": "balanced", "random_state": 42}),
        ("HGB-Balanced", {"max_iter": 120, "max_depth": 7, "learning_rate": 0.05, "l2_regularization": 1.0, "class_weight": "balanced", "random_state": 42}),
        ("HGB-Deep-Regularized", {"max_iter": 150, "max_depth": 9, "learning_rate": 0.03, "l2_regularization": 5.0, "class_weight": "balanced", "random_state": 42})
    ]
    for cfg_name, params in hgb_configs:
        model = HistGradientBoostingClassifier(**params)
        res, trained = evaluate_classifier("HistGradientBoosting", cfg_name, model, X_tr, y_clf_tr, X_va, y_clf_va, X_te, y_clf_te)
        clf_results.append(res)
        trained_clf_models[f"HistGradientBoosting_{cfg_name}"] = trained
        
        reg_params = {k: v for k, v in params.items() if k != "class_weight"}
        reg_model = HistGradientBoostingRegressor(**reg_params)
        r_res, r_trained = evaluate_regressor("HistGradientBoosting", cfg_name, reg_model, X_tr, y_reg_tr, X_va, y_reg_va, X_te, y_reg_te)
        reg_results.append(r_res)
        trained_reg_models[f"HistGradientBoosting_{cfg_name}"] = r_trained

    # =========================================================================
    # 5. RANDOM FOREST CLASSIFIERS & REGRESSORS
    # =========================================================================
    logger.info("\n=== BENCHMARKING RANDOM FOREST ===")
    rf_configs = [
        ("RF-Shallow", {"n_estimators": 50, "max_depth": 6, "max_samples": 0.25, "class_weight": "balanced", "random_state": 42, "n_jobs": -1}),
        ("RF-Balanced", {"n_estimators": 80, "max_depth": 8, "max_samples": 0.25, "min_samples_leaf": 10, "class_weight": "balanced", "random_state": 42, "n_jobs": -1})
    ]
    for cfg_name, params in rf_configs:
        model = RandomForestClassifier(**params)
        res, trained = evaluate_classifier("RandomForest", cfg_name, model, X_tr, y_clf_tr, X_va, y_clf_va, X_te, y_clf_te)
        clf_results.append(res)
        trained_clf_models[f"RandomForest_{cfg_name}"] = trained
        
        reg_params = {k: v for k, v in params.items() if k != "class_weight"}
        reg_model = RandomForestRegressor(**reg_params)
        r_res, r_trained = evaluate_regressor("RandomForest", cfg_name, reg_model, X_tr, y_reg_tr, X_va, y_reg_va, X_te, y_reg_te)
        reg_results.append(r_res)
        trained_reg_models[f"RandomForest_{cfg_name}"] = r_trained

    # =========================================================================
    # 6. NEURAL NETWORK / MLP CLASSIFIER & REGRESSOR
    # =========================================================================
    logger.info("\n=== BENCHMARKING NEURAL NETWORK (MLP) ===")
    mlp_configs = [
        ("MLP-2Layer-Regularized", {"hidden_layer_sizes": (64, 32), "alpha": 0.01, "batch_size": 4096, "max_iter": 15, "random_state": 42, "early_stopping": True}),
        ("MLP-3Layer-Deep", {"hidden_layer_sizes": (128, 64, 32), "alpha": 0.05, "batch_size": 4096, "max_iter": 12, "random_state": 42, "early_stopping": True})
    ]
    # Train MLP on 100k sample representative subset for rapid convergence
    n_mlp = min(100000, len(X_tr_sc))
    X_tr_mlp = X_tr_sc[:n_mlp]
    y_clf_mlp = y_clf_tr[:n_mlp]
    y_reg_mlp = y_reg_tr[:n_mlp]

    for cfg_name, params in mlp_configs:
        model = MLPClassifier(**params)
        res, trained = evaluate_classifier("NeuralNetwork_MLP", cfg_name, model, X_tr_mlp, y_clf_mlp, X_va_sc, y_clf_va, X_te_sc, y_clf_te, is_scaled=True)
        clf_results.append(res)
        trained_clf_models[f"NeuralNetwork_{cfg_name}"] = trained
        
        reg_model = MLPRegressor(**params)
        r_res, r_trained = evaluate_regressor("NeuralNetwork_MLP", cfg_name, reg_model, X_tr_mlp, y_reg_mlp, X_va_sc, y_reg_va, X_te_sc, y_reg_te)
        reg_results.append(r_res)
        trained_reg_models[f"NeuralNetwork_{cfg_name}"] = r_trained

    # =========================================================================
    # 7. REGULARIZED LINEAR BASELINE
    # =========================================================================
    logger.info("\n=== BENCHMARKING REGULARIZED LINEAR BASELINE ===")
    pipe_lr = Pipeline([("lr", LogisticRegression(class_weight="balanced", max_iter=200, random_state=42))])
    res, trained = evaluate_classifier("LogisticRegression", "LR-L2-Baseline", pipe_lr, X_tr_sc, y_clf_tr, X_va_sc, y_clf_va, X_te_sc, y_clf_te, is_scaled=True)
    clf_results.append(res)
    trained_clf_models["LogisticRegression_LR-L2-Baseline"] = trained
    
    pipe_ridge = Pipeline([("ridge", Ridge(alpha=1.0, random_state=42))])
    r_res, r_trained = evaluate_regressor("RidgeRegression", "Ridge-Baseline", pipe_ridge, X_tr_sc, y_reg_tr, X_va_sc, y_reg_va, X_te_sc, y_reg_te)
    reg_results.append(r_res)
    trained_reg_models["RidgeRegression_Ridge-Baseline"] = r_trained

    # =========================================================================
    # WINNER SELECTION: CRITERIA = VAL PR-AUC WITH OVERFITTING GAP <= 0.05
    # =========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("FINAL LEADERBOARD & WINNER SELECTION")
    logger.info("=" * 80)
    
    # Sort classification candidates: non-overfitting first, then by val PR-AUC
    sorted_clf = sorted(
        clf_results,
        key=lambda x: (not x["overfitting"]["is_flagged_overfitting"], x["val"]["pr_auc"]),
        reverse=True
    )
    
    best_clf_info = sorted_clf[0]
    best_clf_key = f"{best_clf_info['model_family']}_{best_clf_info['config_name']}"
    best_clf_model = trained_clf_models[best_clf_key]
    
    # Sort regression candidates by val RMSE
    sorted_reg = sorted(reg_results, key=lambda x: x["val"]["rmse"])
    best_reg_info = sorted_reg[0]
    best_reg_key = f"{best_reg_info['model_family']}_{best_reg_info['config_name']}"
    best_reg_model = trained_reg_models[best_reg_key]
    
    logger.info(f"🏆 WINNING CLASSIFIER: {best_clf_key}")
    logger.info(f"   Val PR-AUC: {best_clf_info['val']['pr_auc']:.4f} | Val ROC-AUC: {best_clf_info['val']['roc_auc']:.4f} | Overfit Gap: {best_clf_info['overfitting']['pr_auc_gap']:+.4f}")
    logger.info(f"   Holdout Test PR-AUC (2025): {best_clf_info['test']['pr_auc']:.4f} | Test ROC-AUC: {best_clf_info['test']['roc_auc']:.4f}")
    
    logger.info(f"🏆 WINNING REGRESSOR: {best_reg_key}")
    logger.info(f"   Val RMSE: {best_reg_info['val']['rmse']:.2f} MW | R2: {best_reg_info['val']['r2']:.4f}")
    logger.info(f"   Holdout Test RMSE (2025): {best_reg_info['test']['rmse']:.2f} MW")
    
    # Save artifacts
    clf_artifact_path = OUTPUT_DIR / "best_wildfire_classifier.joblib"
    joblib.dump({
        "model": best_clf_model,
        "model_key": best_clf_key,
        "feature_cols": FEATURE_COLS,
        "imputer": data["imputer"],
        "scaler": data["scaler"] if "MLP" in best_clf_key or "Logistic" in best_clf_key else None,
        "metrics": best_clf_info,
        "timestamp": datetime.now().isoformat()
    }, clf_artifact_path)
    logger.info(f"Saved best classifier artifact to {clf_artifact_path}")
    
    reg_artifact_path = OUTPUT_DIR / "best_wildfire_regressor.joblib"
    joblib.dump({
        "model": best_reg_model,
        "model_key": best_reg_key,
        "feature_cols": FEATURE_COLS,
        "imputer": data["imputer"],
        "scaler": data["scaler"] if "MLP" in best_reg_key or "Ridge" in best_reg_key else None,
        "metrics": best_reg_info,
        "timestamp": datetime.now().isoformat()
    }, reg_artifact_path)
    logger.info(f"Saved best regressor artifact to {reg_artifact_path}")
    
    # Save comprehensive evaluation JSON
    report = {
        "timestamp": datetime.now().isoformat() + "Z",
        "dataset": {
            "path": str(DB_PATH),
            "train_samples": len(train_df),
            "val_samples": len(val_df),
            "test_samples": len(test_df),
            "features": FEATURE_COLS
        },
        "winning_classifier": best_clf_info,
        "winning_regressor": best_reg_info,
        "classification_leaderboard": sorted_clf,
        "regression_leaderboard": sorted_reg
    }
    
    report_path = OUTPUT_DIR / "model_benchmark_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved full benchmark report to {report_path}")
    
    return report


if __name__ == "__main__":
    run_benchmark()
