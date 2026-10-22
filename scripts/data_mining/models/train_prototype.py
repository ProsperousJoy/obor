"""
Prototype Wildfire Risk Prediction Model Trainer
------------------------------------------------
Trains and evaluates baseline machine learning models directly from the DuckDB
warehouse analytical view (vw_training_dataset).

Evaluates:
1. Random Forest Classifier (balanced weights)
2. HistGradientBoosting Classifier
3. Logistic Regression Baseline
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

import duckdb
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    classification_report
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("model_trainer")

OUTPUT_DIR = Path("outputs/models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_dataset(db_path: str = "data/warehouse/wildfire.duckdb") -> pd.DataFrame:
    """
    Load feature set and targets from DuckDB view vw_training_dataset.
    """
    logger.info(f"Connecting to data warehouse at {db_path}...")
    con = duckdb.connect(db_path, read_only=True)
    
    query = "SELECT * FROM vw_training_dataset"
    logger.info("Querying vw_training_dataset...")
    df = con.execute(query).df()
    logger.info(f"Loaded {len(df):,} samples with {df.shape[1]} columns.")
    return df


def preprocess_data(df: pd.DataFrame):
    """
    Select non-constant features, drop identifiers and target columns.
    """
    exclude = [
        'grid_id', 'target_datetime', 'year', 'month', 'province', 'is_land',
        'target_has_fire_24h', 'target_fire_count_24h', 'target_fire_intensity_24h'
    ]
    # Filter only columns that have more than 1 distinct non-null value
    feature_cols = [c for c in df.columns if c not in exclude and df[c].nunique(dropna=True) > 1]
    logger.info(f"Selected {len(feature_cols)} informative features: {feature_cols}")
    
    X = df[feature_cols].copy()
    y = df['target_has_fire_24h'].astype(int)
    
    return X, y, feature_cols


def train_models(df: pd.DataFrame) -> dict:
    """
    Train and evaluate multiple models on vw_training_dataset.
    """
    X, y, feature_cols = preprocess_data(df)
    
    pos_count = int(y.sum())
    neg_count = len(y) - pos_count
    pos_rate = (pos_count / len(y)) * 100
    logger.info(f"Target distribution: {pos_count} Positive ({pos_rate:.3f}%), {neg_count} Negative")
    
    # Train / Test split (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    logger.info(f"Train samples: {len(X_train):,}, Test samples: {len(X_test):,} (Pos: {y_test.sum()})")
    
    # Impute missing values with median
    imputer = SimpleImputer(strategy="median")
    X_train_imp = pd.DataFrame(imputer.fit_transform(X_train), columns=feature_cols)
    X_test_imp = pd.DataFrame(imputer.transform(X_test), columns=feature_cols)
    
    results = {
        "timestamp": datetime.now().isoformat() + "Z",
        "total_samples": len(df),
        "positive_samples": pos_count,
        "negative_samples": neg_count,
        "features_evaluated": feature_cols,
        "models": {}
    }
    
    # ─────────────────────────────────────────────────────────────
    # Model 1: Random Forest Classifier (Balanced)
    # ─────────────────────────────────────────────────────────────
    logger.info("Training Random Forest Classifier (balanced weights)...")
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train_imp, y_train)
    
    rf_probs = rf.predict_proba(X_test_imp)[:, 1]
    rf_preds = (rf_probs >= 0.5).astype(int)
    cm_rf = confusion_matrix(y_test, rf_preds).tolist()
    
    results["models"]["RandomForest"] = {
        "roc_auc": round(float(roc_auc_score(y_test, rf_probs)), 4),
        "pr_auc": round(float(average_precision_score(y_test, rf_probs)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_test, rf_preds)), 4),
        "confusion_matrix": {
            "tn": cm_rf[0][0], "fp": cm_rf[0][1],
            "fn": cm_rf[1][0], "tp": cm_rf[1][1]
        }
    }
    
    # Feature importances from Random Forest
    rf_feat_imp = sorted(
        [{"feature": f, "importance": round(float(imp), 4)} for f, imp in zip(feature_cols, rf.feature_importances_)],
        key=lambda x: x["importance"],
        reverse=True
    )
    results["top_features"] = rf_feat_imp
    
    # ─────────────────────────────────────────────────────────────
    # Model 2: HistGradientBoosting Classifier
    # ─────────────────────────────────────────────────────────────
    logger.info("Training HistGradientBoosting Classifier...")
    hgb = HistGradientBoostingClassifier(
        max_iter=50,
        max_depth=5,
        class_weight="balanced",
        random_state=42
    )
    hgb.fit(X_train_imp, y_train)
    
    hgb_probs = hgb.predict_proba(X_test_imp)[:, 1]
    hgb_preds = (hgb_probs >= 0.5).astype(int)
    cm_hgb = confusion_matrix(y_test, hgb_preds).tolist()
    
    results["models"]["HistGradientBoosting"] = {
        "roc_auc": round(float(roc_auc_score(y_test, hgb_probs)), 4),
        "pr_auc": round(float(average_precision_score(y_test, hgb_probs)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_test, hgb_preds)), 4),
        "confusion_matrix": {
            "tn": cm_hgb[0][0], "fp": cm_hgb[0][1],
            "fn": cm_hgb[1][0], "tp": cm_hgb[1][1]
        }
    }
    
    # ─────────────────────────────────────────────────────────────
    # Model 3: Logistic Regression (Standardized baseline)
    # ─────────────────────────────────────────────────────────────
    logger.info("Training Logistic Regression Baseline...")
    pipe_lr = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(class_weight="balanced", max_iter=200, random_state=42))
    ])
    pipe_lr.fit(X_train_imp, y_train)
    
    lr_probs = pipe_lr.predict_proba(X_test_imp)[:, 1]
    lr_preds = (lr_probs >= 0.5).astype(int)
    cm_lr = confusion_matrix(y_test, lr_preds).tolist()
    
    results["models"]["LogisticRegression"] = {
        "roc_auc": round(float(roc_auc_score(y_test, lr_probs)), 4),
        "pr_auc": round(float(average_precision_score(y_test, lr_probs)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_test, lr_preds)), 4),
        "confusion_matrix": {
            "tn": cm_lr[0][0], "fp": cm_lr[0][1],
            "fn": cm_lr[1][0], "tp": cm_lr[1][1]
        }
    }
    
    # Save Report
    out_file = OUTPUT_DIR / "prototype_model_evaluation.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Evaluation report saved to {out_file}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Train Prototype Wildfire Risk ML Model")
    parser.add_argument("--db-path", default="data/warehouse/wildfire.duckdb", help="Path to DuckDB warehouse")
    args = parser.parse_args()
    
    df = load_dataset(args.db_path)
    results = train_models(df)
    
    print("\n" + "=" * 70)
    print("PROTOTYPE MACHINE LEARNING MODEL EVALUATION REPORT")
    print(f"Data Warehouse: {args.db_path} (vw_training_dataset)")
    print("=" * 70)
    print(f"Total Grid-Time Samples: {results['total_samples']:,}")
    print(f"Target: target_has_fire_24h in (T, T+24h]")
    print(f"Positive Events (Fires Detected): {results['positive_samples']} ({results['positive_samples']/results['total_samples']*100:.3f}%)")
    print(f"Active Features Tested: {len(results['features_evaluated'])}")
    print("-" * 70)
    print(f"{'Model Architecture':<24} | {'ROC-AUC':<9} | {'PR-AUC':<9} | {'Balanced Acc':<12} | {'TP/Total Pos'}")
    print("-" * 70)
    for model_name, m in results["models"].items():
        tp = m["confusion_matrix"]["tp"]
        tot_pos = tp + m["confusion_matrix"]["fn"]
        print(f"{model_name:<24} | {m['roc_auc']:<9.4f} | {m['pr_auc']:<9.4f} | {m['balanced_accuracy']:<12.4f} | {tp}/{tot_pos}")
    print("-" * 70)
    print("TOP 8 MOST PREDICTIVE FEATURES (Random Forest Importance):")
    for idx, item in enumerate(results["top_features"][:8], 1):
        bar = "=" * int(item["importance"] * 40)
        print(f"  {idx}. {item['feature']:<25} : {item['importance']*100:>5.1f}%  [{bar}]")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
