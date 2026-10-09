"""
train_stage_aware_candidate_remediated.py
-------------------------------------------
Stage 2D.1 Remediated Candidate Model Training & Evaluation.

Trains the remediated stage-aware candidate ML model with canonical category semantics:
- Estimator: HistGradientBoostingClassifier (native NaN attendance handling)
- Dataset: data_real/jan_niti_stage_aware_dataset_remediated.csv (12,000 records)
- Canonical Categories: ['EWS', 'General', 'OBC', 'SC', 'ST']
- Split: Stratified 70% Train (8,400) / 15% Validation (1,800) / 15% Holdout Test (1,800)
- Preserves: model/model_v2.pkl (Untouched legacy production model)
- Preserves: model/model_stage_aware_candidate.pkl (Untouched Stage 2C candidate reference)
- Artifacts Produced:
  - model/model_stage_aware_candidate_remediated.pkl
  - model/encoders_stage_aware_candidate_remediated.pkl
  - model/stage_aware_remediated_training_report.json
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
    confusion_matrix,
    log_loss,
    brier_score_loss,
    classification_report,
)
import shap

DATA_PATH = "data_real/jan_niti_stage_aware_dataset_remediated.csv"
MODEL_OUT = "model/model_stage_aware_candidate_remediated.pkl"
ENCODERS_OUT = "model/encoders_stage_aware_candidate_remediated.pkl"
REPORT_OUT = "model/stage_aware_remediated_training_report.json"
SEED = 42

# 10 Agreed Feature Columns
FEATURE_COLS = [
    "academic_stage",
    "qualification_type",
    "academic_score",
    "previous_score",
    "attendance",
    "is_attendance_applicable",
    "annual_income",
    "application_category",
    "scholarship_scheme",
    "documents_verified",
]

CATEGORICAL_COLS = [
    "academic_stage",
    "qualification_type",
    "application_category",
    "scholarship_scheme",
    "documents_verified",
]

TARGET_COL = "decision"


def main():
    print(f"Loading remediated dataset from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"Dataset shape: {df.shape}")

    # Build and fit reproducible encoders
    encoders = {}
    df_encoded = df.copy()

    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df_encoded[col] = le.fit_transform(df_encoded[col].astype(str))
        encoders[col] = le
        print(f"Encoder '{col}' classes: {list(le.classes_)}")

    target_encoder = LabelEncoder()
    df_encoded[TARGET_COL] = target_encoder.fit_transform(df_encoded[TARGET_COL])
    encoders["target"] = target_encoder
    print(f"Target encoder classes: {list(target_encoder.classes_)}")

    # Verify canonical categories
    cat_classes = list(encoders["application_category"].classes_)
    expected_cats = ["EWS", "General", "OBC", "SC", "ST"]
    assert sorted(cat_classes) == sorted(expected_cats), f"Category mismatch: {cat_classes} != {expected_cats}"
    print("\nCanonical category encoder verified successfully: ['EWS', 'General', 'OBC', 'SC', 'ST']")

    # Save feature columns metadata inside encoders bundle
    encoders["feature_cols"] = FEATURE_COLS
    encoders["categorical_cols"] = CATEGORICAL_COLS

    # Stratified Train (70%) / Validation (15%) / Holdout Test (15%)
    train_idx, temp_idx = train_test_split(
        np.arange(len(df)),
        test_size=0.30,
        random_state=SEED,
        stratify=df_encoded[TARGET_COL],
    )

    val_idx, test_idx = train_test_split(
        temp_idx,
        test_size=0.50,
        random_state=SEED,
        stratify=df_encoded.iloc[temp_idx][TARGET_COL],
    )

    print(f"\nSplit sizes: Train={len(train_idx)} (70%), Val={len(val_idx)} (15%), Test={len(test_idx)} (15%)")

    # Strict zero leakage check
    train_ids = set(df.iloc[train_idx]["application_id"])
    val_ids = set(df.iloc[val_idx]["application_id"])
    test_ids = set(df.iloc[test_idx]["application_id"])
    assert len(train_ids.intersection(val_ids)) == 0, "ID overlap between train and val!"
    assert len(train_ids.intersection(test_ids)) == 0, "ID overlap between train and test!"
    assert len(val_ids.intersection(test_ids)) == 0, "ID overlap between val and test!"
    print("Zero applicant ID overlap across Train, Val, and Test confirmed.")

    X_train = df_encoded.iloc[train_idx][FEATURE_COLS]
    y_train = df_encoded.iloc[train_idx][TARGET_COL]

    X_val = df_encoded.iloc[val_idx][FEATURE_COLS]
    y_val = df_encoded.iloc[val_idx][TARGET_COL]

    X_test = df_encoded.iloc[test_idx][FEATURE_COLS]
    y_test = df_encoded.iloc[test_idx][TARGET_COL]

    # Training HistGradientBoosting
    print("\nTraining HistGradientBoostingClassifier candidate model...")
    candidate_model = HistGradientBoostingClassifier(
        max_iter=150,
        max_depth=6,
        learning_rate=0.08,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=SEED,
    )
    candidate_model.fit(X_train, y_train)

    # Evaluate on Holdout Test Set
    print("\nEvaluating on untouched Holdout Test Set (1,800 rows)...")
    y_test_pred = candidate_model.predict(X_test)
    y_test_proba = candidate_model.predict_proba(X_test)

    target_classes = list(target_encoder.classes_)
    approve_idx = target_classes.index("APPROVE")

    acc = accuracy_score(y_test, y_test_pred)
    prec, rec, f1, supp = precision_recall_fscore_support(y_test, y_test_pred, average="macro")
    per_class_p, per_class_r, per_class_f1, _ = precision_recall_fscore_support(y_test, y_test_pred, average=None)
    ll = log_loss(y_test, y_test_proba)
    brier = brier_score_loss((y_test == approve_idx).astype(int), y_test_proba[:, approve_idx])
    cm = confusion_matrix(y_test, y_test_pred).tolist()

    print(f"Overall Test Accuracy: {acc:.4f}")
    print(f"Overall Macro Precision: {prec:.4f}")
    print(f"Overall Macro Recall: {rec:.4f}")
    print(f"Overall Macro F1: {f1:.4f}")
    print(f"Multiclass Log Loss: {ll:.4f}")
    print(f"Brier Score for P(APPROVE): {brier:.4f}")

    print("\nClassification Report:")
    print(classification_report(y_test, y_test_pred, target_names=target_classes))

    # Evaluate by Stage Cohort
    test_df_orig = df.iloc[test_idx].copy()
    stage_metrics = {}
    for stage_name in ["FIRST_YEAR", "SECOND_YEAR", "THIRD_YEAR", "FOURTH_YEAR", "POSTGRADUATE"]:
        idx_mask = (test_df_orig["academic_stage"] == stage_name).values
        sub_indices = np.where(idx_mask)[0]
        y_sub = y_test.iloc[sub_indices]
        y_sub_pred = y_test_pred[sub_indices]
        y_sub_proba = y_test_proba[sub_indices]

        sub_acc = accuracy_score(y_sub, y_sub_pred)
        sub_f1 = f1_score(y_sub, y_sub_pred, average="macro")
        sub_ll = log_loss(y_sub, y_sub_proba)
        sub_brier = brier_score_loss((y_sub == approve_idx).astype(int), y_sub_proba[:, approve_idx])

        stage_metrics[stage_name] = {
            "rows": len(sub_indices),
            "accuracy": round(sub_acc, 4),
            "macro_f1": round(sub_f1, 4),
            "log_loss": round(sub_ll, 4),
            "brier_score": round(sub_brier, 4),
        }
        print(f"Stage {stage_name} ({len(sub_indices)} rows): Acc={sub_acc:.4f}, F1={sub_f1:.4f}, LogLoss={sub_ll:.4f}, Brier={sub_brier:.4f}")

    # Evaluate by Social Category
    category_metrics = {}
    for cat_name in expected_cats:
        idx_mask = (test_df_orig["application_category"] == cat_name).values
        sub_indices = np.where(idx_mask)[0]
        y_sub = y_test.iloc[sub_indices]
        y_sub_pred = y_test_pred[sub_indices]
        y_sub_proba = y_test_proba[sub_indices]

        sub_acc = accuracy_score(y_sub, y_sub_pred)
        sub_f1 = f1_score(y_sub, y_sub_pred, average="macro")
        sub_ll = log_loss(y_sub, y_sub_proba)
        sub_brier = brier_score_loss((y_sub == approve_idx).astype(int), y_sub_proba[:, approve_idx])

        category_metrics[cat_name] = {
            "rows": len(sub_indices),
            "accuracy": round(sub_acc, 4),
            "macro_f1": round(sub_f1, 4),
            "log_loss": round(sub_ll, 4),
            "brier_score": round(sub_brier, 4),
        }
        print(f"Category {cat_name} ({len(sub_indices)} rows): Acc={sub_acc:.4f}, F1={sub_f1:.4f}, LogLoss={sub_ll:.4f}, Brier={sub_brier:.4f}")

    # TreeSHAP Verification on Remediated Candidate Model
    print("\nVerifying TreeSHAP explainability...")
    explainer = shap.TreeExplainer(candidate_model)
    sample_X = X_test.iloc[:10]
    shap_vals = explainer.shap_values(sample_X)
    print("TreeSHAP computed successfully on candidate model!")
    print(f"SHAP values structure: shape={getattr(shap_vals, 'shape', len(shap_vals))}")
    print(f"Base value: {explainer.expected_value}")

    # Save artifacts
    print(f"\nSaving remediated candidate model to {MODEL_OUT}...")
    joblib.dump(candidate_model, MODEL_OUT)

    print(f"Saving remediated candidate encoders to {ENCODERS_OUT}...")
    joblib.dump(encoders, ENCODERS_OUT)

    report_data = {
        "candidate_model_path": MODEL_OUT,
        "encoders_path": ENCODERS_OUT,
        "dataset_path": DATA_PATH,
        "estimator": "HistGradientBoostingClassifier",
        "dataset_rows": len(df),
        "train_rows": len(train_idx),
        "val_rows": len(val_idx),
        "test_rows": len(test_idx),
        "features": FEATURE_COLS,
        "categorical_features": CATEGORICAL_COLS,
        "canonical_categories": expected_cats,
        "target_classes": target_classes,
        "overall_metrics": {
            "accuracy": round(acc, 4),
            "macro_precision": round(prec, 4),
            "macro_recall": round(rec, 4),
            "macro_f1": round(f1, 4),
            "log_loss": round(ll, 4),
            "brier_score_p_approve": round(brier, 4),
        },
        "per_class_metrics": {
            cls: {
                "precision": round(per_class_p[i], 4),
                "recall": round(per_class_r[i], 4),
                "f1": round(per_class_f1[i], 4),
            }
            for i, cls in enumerate(target_classes)
        },
        "confusion_matrix": cm,
        "stage_metrics": stage_metrics,
        "category_metrics": category_metrics,
    }

    with open(REPORT_OUT, "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"Saved evaluation report to {REPORT_OUT}")


if __name__ == "__main__":
    main()
