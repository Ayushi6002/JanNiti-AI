"""
stage_aware_candidate_service.py
---------------------------------
Isolated Prediction & TreeSHAP Explainability Service for the Candidate Model.

Designed for Stage 2C validation:
- Loads model/model_stage_aware_candidate.pkl and model/encoders_stage_aware_candidate.pkl
- Exposes predict_and_explain(raw_input) and explain(raw_input)
- TreeSHAP integration for all 10 features, with native handling of NaN attendance
- Human-friendly explainability labels conforming to Section 18
- ZERO interference with production ml_service or model_v2.pkl
"""

import os
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import joblib
import shap
from backend.ml_service import normalize_document_status

MODEL_PATH = "model/model_stage_aware_candidate_remediated.pkl"
ENCODERS_PATH = "model/encoders_stage_aware_candidate_remediated.pkl"

FEATURE_DISPLAY_NAMES = {
    "academic_stage": "Academic Stage",
    "qualification_type": "Qualification Type",
    "academic_score": "Academic Performance",
    "previous_score": "Previous Academic Record",
    "attendance": "College Attendance",
    "is_attendance_applicable": "Attendance Availability",
    "annual_income": "Annual Family Income",
    "application_category": "Social Category",
    "scholarship_scheme": "Scholarship Scheme",
    "documents_verified": "Document Verification Status",
}

# Canonical Social Categories for Stage 2D.1 Remediated Candidate Model
# Strictly preserves distinct constitutional groups: General, OBC, SC, ST, EWS
CATEGORY_MAP = {
    "GENERAL": "General",
    "GEN": "General",
    "OPEN": "General",
    "UNRESERVED": "General",
    "UR": "General",
    "OBC": "OBC",
    "OTHER BACKWARD CLASS": "OBC",
    "OTHER BACKWARD CLASSES": "OBC",
    "OTHER BACKWARD CATEGORY": "OBC",
    "SC": "SC",
    "SCHEDULED CASTE": "SC",
    "SCHEDULED CASTES": "SC",
    "ST": "ST",
    "SCHEDULED TRIBE": "ST",
    "SCHEDULED TRIBES": "ST",
    "EWS": "EWS",
    "ECONOMICALLY WEAKER": "EWS",
    "ECONOMICALLY_WEAKER": "EWS",
    "ECONOMICALLY WEAKER SECTION": "EWS",
    "ECONOMICALLY WEAKER SECTIONS": "EWS",
    "MERIT": "General",
    "SPECIAL CIRCUMSTANCE": "General",
    "SPECIAL_CIRCUMSTANCE": "General",
    "CATEGORY": "General",
}

SCHEME_MAP = {
    "Merit Scholarship": "Merit Scholarship",
    "MERIT": "Merit Scholarship",
    "Need Based Scholarship": "Need-Based Scholarship",
    "Need-Based Scholarship": "Need-Based Scholarship",
    "NEED_BASED": "Need-Based Scholarship",
    "Category Based Scholarship": "Academic Support Scholarship",
    "Category-Based Scholarship": "Academic Support Scholarship",
    "Academic Support Scholarship": "Academic Support Scholarship",
    "CATEGORY": "Academic Support Scholarship",
}


class StageAwareCandidateService:

    def __init__(self):
        self.model = None
        self.encoders = None
        self.explainer = None
        self._load_artifacts()

    def _load_artifacts(self):
        if os.path.exists(MODEL_PATH) and os.path.exists(ENCODERS_PATH):
            self.model = joblib.load(MODEL_PATH)
            self.encoders = joblib.load(ENCODERS_PATH)
            self.explainer = shap.TreeExplainer(self.model)
            self.feature_cols = self.encoders["feature_cols"]
            self.categorical_cols = self.encoders["categorical_cols"]
            self.classes = list(self.encoders["target"].classes_)
            self.approve_idx = self.classes.index("APPROVE")

    def normalize_input(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw input into the candidate model's 10-feature schema."""
        data = dict(raw_input)

        stage = str(data.get("academic_stage", "FIRST_YEAR")).strip().upper()
        if stage not in ["FIRST_YEAR", "SECOND_YEAR", "THIRD_YEAR", "FOURTH_YEAR", "POSTGRADUATE"]:
            stage = "FIRST_YEAR"

        qtype = str(data.get("qualification_type", "NOT_APPLICABLE")).strip().upper()
        if qtype == "HSC":
            qtype = "HSC_12TH"
        if stage != "FIRST_YEAR":
            qtype = "NOT_APPLICABLE"
        elif qtype not in ["HSC_12TH", "DIPLOMA", "OTHER"]:
            qtype = "HSC_12TH"

        acad_score = float(data.get("academic_score", data.get("qualifying_score", 75.0)))
        prev_score = float(data.get("previous_score", data.get("ssc_score", acad_score)))

        att_raw = data.get("attendance")
        if stage == "FIRST_YEAR" or att_raw is None or str(att_raw).strip() in ("", "None", "nan"):
            attendance = np.nan
            is_att_app = 0
        else:
            attendance = float(att_raw)
            is_att_app = 1

        income = float(data.get("annual_income", 300000.0))

        cat_raw = str(data.get("application_category", "General")).strip()
        cat_norm = CATEGORY_MAP.get(cat_raw.upper(), "General")
        if cat_norm not in self.encoders["application_category"].classes_:
            cat_norm = "General"

        sch_raw = str(data.get("scholarship_scheme", "Merit Scholarship")).strip()
        sch_norm = SCHEME_MAP.get(sch_raw, "Merit Scholarship")
        if sch_norm not in self.encoders["scholarship_scheme"].classes_:
            sch_norm = "Merit Scholarship"

        docs_val = data.get("documents_verified")
        caller_contract = data.get("documents_verified_contract") or data.get("caller_contract")
        docs_raw = normalize_document_status(docs_val, caller_contract=caller_contract)

        return {
            "academic_stage": stage,
            "qualification_type": qtype,
            "academic_score": acad_score,
            "previous_score": prev_score,
            "attendance": attendance,
            "is_attendance_applicable": is_att_app,
            "annual_income": income,
            "application_category": cat_norm,
            "scholarship_scheme": sch_norm,
            "documents_verified": docs_raw,
        }

    def encode_input(self, normalized: Dict[str, Any]) -> pd.DataFrame:
        row = {}
        for col in self.feature_cols:
            val = normalized[col]
            if col in self.categorical_cols:
                le = self.encoders[col]
                # Fallback to class 0 if unseen
                try:
                    enc_val = int(le.transform([str(val)])[0])
                except Exception:
                    enc_val = 0
                row[col] = enc_val
            else:
                row[col] = float(val) if not np.isnan(val) else np.nan
        return pd.DataFrame([row])

    def predict_and_explain(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.normalize_input(raw_input)
        X = self.encode_input(normalized)

        probas = self.model.predict_proba(X)[0]
        pred_idx = int(self.model.predict(X)[0])
        predicted_class = self.classes[pred_idx]

        prob_approve = float(probas[self.approve_idx])
        prob_dict = {cls: round(float(p), 4) for cls, p in zip(self.classes, probas)}

        # TreeSHAP computation
        shap_vals = self.explainer.shap_values(X)  # shape (1, 10, 3)
        class_shap = shap_vals[0, :, pred_idx]
        base_val = float(self.explainer.expected_value[pred_idx])

        features_explained = []
        for i, feat_name in enumerate(self.feature_cols):
            s_val = float(class_shap[i])
            disp_name = FEATURE_DISPLAY_NAMES.get(feat_name, feat_name.replace("_", " ").title())
            inp_val = normalized[feat_name]

            if feat_name == "attendance" and np.isnan(inp_val):
                human_expl = "College attendance is not available because this is a fresh-admission application."
                formatted_inp = "Not applicable (waived)"
                direction = "neutral"
            else:
                formatted_inp = str(inp_val)
                if s_val > 0.01:
                    direction = "positive"
                    human_expl = f"{disp_name} supported the {predicted_class} assessment."
                elif s_val < -0.01:
                    direction = "negative"
                    human_expl = f"{disp_name} pushed against the {predicted_class} assessment."
                else:
                    direction = "neutral"
                    human_expl = f"{disp_name} had a neutral influence on this assessment."

            features_explained.append({
                "feature": feat_name,
                "display_name": disp_name,
                "input_value": formatted_inp,
                "shap_value": round(s_val, 4),
                "direction": direction,
                "human_explanation": human_expl,
            })

        # Sort features by absolute impact
        features_explained.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

        return {
            "prediction": predicted_class,
            "decision": predicted_class,
            "estimated_approval_probability": round(prob_approve, 4),
            "class_probabilities": prob_dict,
            "normalized_input": normalized,
            "tree_shap": {
                "base_value": round(base_val, 4),
                "predicted_class": predicted_class,
                "features": features_explained,
            },
        }


candidate_service = StageAwareCandidateService()
