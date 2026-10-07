"""
ml_service.py
----------------
Loads the trained model + encoders once at startup, and exposes a single
function `predict_and_explain()` that the Flask routes call.

This is where the model's raw prediction gets turned into the final
decision the applicant/admin sees - combining:
  1. The model's own prediction + confidence (predict_proba)
  2. SHAP explanation -> plain-language top reasons
  3. Hard override rules (Needs Review triggers) that sit ON TOP of the
     model and can override it - these are deliberately NOT learned by
     the model, they are safety/guardrail checks (see project plan,
     section 1: "ML for judgment, rules for safety-critical checks").
"""

from pathlib import Path

import joblib
import pandas as pd
import shap

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "model"

MODEL_PATH = str(MODEL_DIR / "model_v2.pkl")
ENCODERS_PATH = str(MODEL_DIR / "encoders_v2.pkl")
FEATURE_COLS_PATH = str(MODEL_DIR / "feature_cols_v2.pkl")

CATEGORICAL_COLS = ["application_category", "scholarship_scheme", "documents_verified"]

# Confidence threshold: if the model's top-class probability is below this,
# force the case into Needs Review regardless of predicted class.
CONFIDENCE_THRESHOLD = 0.60

# Document statuses that must never result in a final APPROVE, no matter
# how confident the model is - this is a hard safety rule, not learned.
BLOCKING_DOC_STATUSES = {"INCOMPLETE"}


class MLService:
    def __init__(self):
        self.model = joblib.load(MODEL_PATH)
        self.encoders = joblib.load(ENCODERS_PATH)
        self.feature_cols = joblib.load(FEATURE_COLS_PATH)
        self.explainer = shap.TreeExplainer(self.model)

    def _encode_input(self, raw: dict) -> pd.DataFrame:
        """Convert raw form-style input into the exact encoded format the
        model was trained on. Field names/values must match training data."""
        row = {}
        for col in self.feature_cols:
            if col not in raw:
                raise ValueError(f"Missing required field: {col}")
            row[col] = raw[col]

        for col in CATEGORICAL_COLS:
            le = self.encoders[col]
            val = row[col]
            if val not in le.classes_:
                matched = False
                for cls_name in le.classes_:
                    if str(cls_name).strip().lower() == str(val).strip().lower():
                        val = cls_name
                        matched = True
                        break
                if not matched:
                    raise ValueError(
                        f"Invalid value '{row[col]}' for field '{col}'. "
                        f"Expected one of: {list(le.classes_)}"
                    )
            row[col] = le.transform([val])[0]

        return pd.DataFrame([row])[self.feature_cols]

    def _shap_reasons(self, X: pd.DataFrame, class_idx: int, top_n=3):
        shap_values = self.explainer.shap_values(X)

        if isinstance(shap_values, list):
            values_for_class = shap_values[class_idx][0]
        else:
            values_for_class = shap_values[0, :, class_idx]

        impact = list(zip(self.feature_cols, values_for_class))
        impact.sort(key=lambda x: abs(x[1]), reverse=True)
        top = impact[:top_n]

        reasons = []
        for feat, val in top:
            direction = "increased" if val > 0 else "decreased"
            reasons.append({
                "feature": feat,
                "direction": direction,
                "impact": round(float(val), 3),
            })
        return reasons

    def predict_and_explain(self, raw_input: dict) -> dict:
        X = self._encode_input(raw_input)

        pred_encoded = self.model.predict(X)[0]
        proba = self.model.predict_proba(X)[0]
        model_decision = self.encoders["target"].inverse_transform([pred_encoded])[0]
        confidence = float(proba.max())

        reasons = self._shap_reasons(X, pred_encoded)

        # ---- Apply hard override rules on top of the model's output ----
        final_decision = model_decision
        override_applied = None

        doc_status = raw_input.get("documents_verified")

        if doc_status in BLOCKING_DOC_STATUSES and final_decision == "APPROVE":
            final_decision = "NEEDS_HUMAN_REVIEW"
            override_applied = "Blocked auto-approval: required documents incomplete."

        elif confidence < CONFIDENCE_THRESHOLD and final_decision != "NEEDS_HUMAN_REVIEW":
            final_decision = "NEEDS_HUMAN_REVIEW"
            override_applied = (
                f"Model confidence ({confidence:.2f}) below threshold "
                f"({CONFIDENCE_THRESHOLD}) - routed to human review."
            )

        return {
            "model_decision": model_decision,       # what the model alone predicted
            "final_decision": final_decision,        # after safety-rule overrides
            "confidence": round(confidence, 3),
            "top_reasons": reasons,
            "override_applied": override_applied,     # None if model's decision stood as-is
        }


# Singleton instance - loaded once when the Flask app starts
ml_service = MLService()
