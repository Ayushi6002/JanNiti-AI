"""
Scholarship Decision Model - Training Script (v2)
----------------------------------------------------
Trained on the real dataset built by the teammate (JAN_NITI_FINAL_DECISION_
DATASET_fixed.csv), where `decision` labels have been corrected so that
`documents_verified` is a genuine, learnable signal (see fix_document_labels.py
for details on why/how).

Run this AFTER fix_document_labels.py has produced the _fixed.csv file.
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

DATA_PATH = "data_real/JAN_NITI_FINAL_DECISION_DATASET_fixed.csv"
MODEL_OUT = "model/model_v2.pkl"
ENCODERS_OUT = "model/encoders_v2.pkl"

# These are the ONLY columns the model is trained on.
# NOTE: 'audit_group' and 'application_id' are intentionally excluded.
# audit_group is a proxy attribute used only for the fairness audit below,
# never as a model input. application_id is just a record identifier.
FEATURE_COLS = [
    "academic_score",
    "previous_score",
    "attendance",
    "annual_income",
    "application_category",
    "scholarship_scheme",
    "documents_verified",
]
TARGET_COL = "decision"
CATEGORICAL_COLS = ["application_category", "scholarship_scheme", "documents_verified"]


def load_and_prepare(path):
    df = pd.read_csv(path)
    encoders = {}

    df_encoded = df.copy()
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df_encoded[col] = le.fit_transform(df_encoded[col])
        encoders[col] = le

    target_encoder = LabelEncoder()
    df_encoded[TARGET_COL] = target_encoder.fit_transform(df_encoded[TARGET_COL])
    encoders["target"] = target_encoder

    return df, df_encoded, encoders


def main():
    print("Loading data...")
    df_raw, df, encoders = load_and_prepare(DATA_PATH)

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, df.index, test_size=0.2, random_state=42, stratify=y
    )

    print("Training RandomForestClassifier...")
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    # ---- Evaluation ----
    y_pred = model.predict(X_test)
    target_names = encoders["target"].classes_

    print("\n=== Evaluation ===")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.3f}")
    print("\nClassification report:")
    print(classification_report(y_test, y_pred, target_names=target_names))
    print("Confusion matrix (rows=actual, cols=predicted):")
    cm = confusion_matrix(y_test, y_pred)
    print(pd.DataFrame(cm, index=target_names, columns=target_names))

    # ---- Feature importance ----
    print("\n=== Feature Importances ===")
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS)
    print(importances.sort_values(ascending=False).round(3))

    # ---- Fairness Audit (using 'audit_group' - NOT a training feature) ----
    print("\n=== Fairness Audit (by audit_group, audit-only attribute) ===")
    audit_df = df_raw.loc[idx_test].copy()
    audit_df["predicted"] = encoders["target"].inverse_transform(y_pred)
    approval_rate = (
        audit_df.assign(is_approved=lambda d: d["predicted"] == "APPROVE")
        .groupby("audit_group")["is_approved"]
        .mean()
        .round(3)
    )
    print("Approval rate by audit_group (should be reasonably similar across groups):")
    print(approval_rate)
    max_gap = approval_rate.max() - approval_rate.min()
    print(f"\nMax approval-rate gap across audit_group: {max_gap:.3f}")
    if max_gap > 0.15:
        print("WARNING: gap exceeds 0.15 - flag this in the report as a fairness finding.")
    else:
        print("Gap is within a reasonable range.")

    # ---- Save model + encoders ----
    joblib.dump(model, MODEL_OUT)
    joblib.dump(encoders, ENCODERS_OUT)
    joblib.dump(FEATURE_COLS, "model/feature_cols_v2.pkl")
    print(f"\nSaved model to {MODEL_OUT}")
    print(f"Saved encoders to {ENCODERS_OUT}")


if __name__ == "__main__":
    main()
