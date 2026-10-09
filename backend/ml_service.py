"""
ml_service.py
----------------
Versioned ML Service for Jan Niti AI.

Supports explicit, version-controlled model selection:
- LEGACY MODEL: 'legacy_v2' (model/model_v2.pkl + encoders_v2.pkl, 7 features)
- CANDIDATE MODEL: 'stage_aware_v1' (model/model_stage_aware_candidate.pkl + encoders_stage_aware_candidate.pkl, 10 features)

Configured through a single clear configuration point:
  ACTIVE_MODEL_VERSION = os.getenv("JANNITI_ACTIVE_MODEL_VERSION", "legacy_v2")

Guarantees:
1. Versioned configuration with zero scattered path logic.
2. Controlled rollback safety: switching between models is a single variable or set_active_version() call.
3. Strict P(APPROVE) semantics: approval probability is always proba[approve_idx].
4. Native support for First-Year applicants with missing attendance under stage_aware_v1.
5. Strict governance: hard safety overrides (e.g. INCOMPLETE documents -> NEEDS_HUMAN_REVIEW).
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd
import shap

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "model"

# Single Configuration Point for Production Model Selection
# Default active model is legacy_v2 per Stage 2D.4 release gate policy
ACTIVE_MODEL_VERSION = os.getenv("JANNITI_ACTIVE_MODEL_VERSION", "legacy_v2")

CONFIDENCE_THRESHOLD = 0.60
BLOCKING_DOC_STATUSES = {"INCOMPLETE"}


def normalize_document_status(val: Any, caller_contract: Optional[str] = None) -> str:
    """
    Strict Document Status Normalization Semantics (Stage 2D.4):
    - VERIFIED: The document verification workflow has actually verified the required documents.
    - INCOMPLETE: The required documents are known to be missing or incomplete.
    - UNCERTAIN: Verification has not occurred, the status is unavailable, or the system cannot establish a valid verification result.

    Rules:
    - Missing/None/null/nan -> UNCERTAIN (never silently VERIFIED).
    - Unknown/malformed string (e.g. 'PENDING', 'UNKNOWN', 'INVALID') -> UNCERTAIN (never silently VERIFIED).
    - For boolean inputs:
      * True -> VERIFIED only when caller contract explicitly guarantees successful verification by the verification service.
      * False -> INCOMPLETE only when caller contract explicitly defines it as known incomplete status.
      * Otherwise -> UNCERTAIN.
    """
    if val is None:
        return "UNCERTAIN"

    if isinstance(val, float) and np.isnan(val):
        return "UNCERTAIN"

    contract_norm = str(caller_contract).strip().upper() if caller_contract else ""
    is_verified_contract = contract_norm in ("VERIFIED_SERVICE", "VERIFIED_WORKFLOW", "VERIFIED_GUARANTEED")
    is_incomplete_contract = contract_norm in ("KNOWN_INCOMPLETE", "VERIFIED_SERVICE", "VERIFIED_WORKFLOW", "VERIFIED_GUARANTEED")

    if isinstance(val, bool):
        if val is True:
            return "VERIFIED" if is_verified_contract else "UNCERTAIN"
        else:
            return "INCOMPLETE" if is_incomplete_contract else "UNCERTAIN"

    s = str(val).strip().upper()
    if s in ("", "NONE", "NULL", "NAN"):
        return "UNCERTAIN"

    if s in ("VERIFIED", "MATCH"):
        return "VERIFIED"

    if s in ("INCOMPLETE", "MISSING"):
        return "INCOMPLETE"

    if s == "UNCERTAIN":
        return "UNCERTAIN"

    if s in ("TRUE", "1"):
        return "VERIFIED" if is_verified_contract else "UNCERTAIN"

    if s in ("FALSE", "0"):
        return "INCOMPLETE" if is_incomplete_contract else "UNCERTAIN"

    # Any unknown/malformed string (e.g., 'PENDING', 'UNKNOWN', 'SUBMITTED', etc.)
    return "UNCERTAIN"

STAGE_AWARE_FEATURE_NAMES = {
    "academic_stage": "Academic Stage",
    "qualification_type": "Qualification Type",
    "academic_score": "Academic Score",
    "previous_score": "Previous Academic Score",
    "attendance": "College Attendance",
    "is_attendance_applicable": "Attendance Availability",
    "annual_income": "Annual Family Income",
    "application_category": "Social Category",
    "scholarship_scheme": "Scholarship Scheme",
    "documents_verified": "Document Verification Status",
}

# Canonical Social Category Normalization Map for Stage-Aware Candidate Model
# Strictly preserves distinct constitutional groups: General, OBC, SC, ST, EWS
CANONICAL_CATEGORY_MAP = {
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
    # Backward compatibility mappings for legacy non-social tokens
    "MERIT": "General",
    "SPECIAL CIRCUMSTANCE": "General",
    "SPECIAL_CIRCUMSTANCE": "General",
    "CATEGORY": "General",
}

# Legacy Adapter Map (Used exclusively by legacy_v2 to satisfy 4-class legacy encoder)
LEGACY_CATEGORY_NORMALIZATION_MAP = {
    "GENERAL": "General",
    "MERIT": "Merit",
    "ECONOMICALLY WEAKER": "Economically Weaker",
    "ECONOMICALLY_WEAKER": "Economically Weaker",
    "EWS": "Economically Weaker",
    "SPECIAL CIRCUMSTANCE": "Special Circumstance",
    "SPECIAL_CIRCUMSTANCE": "Special Circumstance",
    "CATEGORY": "Special Circumstance",
    "SC": "Special Circumstance",
    "ST": "Special Circumstance",
    "OBC": "Special Circumstance",
}

# Backward compatibility alias
CATEGORY_NORMALIZATION_MAP = LEGACY_CATEGORY_NORMALIZATION_MAP

SCHEME_NORMALIZATION_MAP = {
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


class MLService:
    def __init__(self, version: Optional[str] = None):
        self.active_version = None
        self.model = None
        self.encoders = None
        self.feature_cols = None
        self.categorical_cols = None
        self.classes = None
        self.approve_idx = 0
        self.explainer = None
        self.set_active_version(version or ACTIVE_MODEL_VERSION)

    def set_active_version(self, version: str):
        """
        Single configuration point for model selection and rollback.
        Accepts: 'legacy_v2' or 'stage_aware_v1'.
        """
        if version == "stage_aware_v1":
            # Stage 2D.1 Remediated Candidate Model Artifacts exclusively
            model_path = MODEL_DIR / "model_stage_aware_candidate_remediated.pkl"
            encoders_path = MODEL_DIR / "encoders_stage_aware_candidate_remediated.pkl"

            if not model_path.exists() or not encoders_path.exists():
                raise FileNotFoundError("Remediated stage-aware candidate model artifacts not found.")

            self.model = joblib.load(str(model_path))
            self.encoders = joblib.load(str(encoders_path))
            self.feature_cols = list(self.encoders["feature_cols"])
            self.categorical_cols = list(self.encoders["categorical_cols"])
            self.classes = list(self.encoders["target"].classes_)
            self.approve_idx = self.classes.index("APPROVE")
            self.explainer = shap.TreeExplainer(self.model)
            self.model_path = str(model_path)
            self.encoders_path = str(encoders_path)
            self.active_version = "stage_aware_v1"

        elif version in ("legacy_v2", "jan_niti_rf_v2"):
            model_path = MODEL_DIR / "model_v2.pkl"
            encoders_path = MODEL_DIR / "encoders_v2.pkl"
            feature_cols_path = MODEL_DIR / "feature_cols_v2.pkl"

            if not model_path.exists() or not encoders_path.exists() or not feature_cols_path.exists():
                raise FileNotFoundError("Legacy production model artifacts not found.")

            self.model = joblib.load(str(model_path))
            self.encoders = joblib.load(str(encoders_path))
            self.feature_cols = list(joblib.load(str(feature_cols_path)))
            self.categorical_cols = ["application_category", "scholarship_scheme", "documents_verified"]
            self.classes = list(self.encoders["target"].classes_)
            self.approve_idx = self.classes.index("APPROVE")
            self.explainer = shap.TreeExplainer(self.model)
            self.model_path = str(model_path)
            self.encoders_path = str(encoders_path)
            self.active_version = "legacy_v2"

        else:
            raise ValueError(f"Unknown model version: '{version}'. Must be 'legacy_v2' or 'stage_aware_v1'.")

    def _encode_input(self, raw: dict) -> pd.DataFrame:
        """
        Convert raw input into the exact encoded feature vector expected by the active model.
        Supports both 7-feature legacy schema and 10-feature stage-aware schema.
        """
        if self.active_version == "stage_aware_v1":
            # Stage-aware 10-feature encoding
            row = {}
            # Check required fields with backward-compatible defaults
            stage_raw = raw.get("academic_stage")
            if stage_raw is None:
                stage = "SECOND_YEAR" if raw.get("attendance") is not None else "FIRST_YEAR"
            else:
                stage = str(stage_raw).strip().upper()
                if stage not in self.encoders["academic_stage"].classes_:
                    raise ValueError(f"Invalid academic_stage: '{stage_raw}'. Supported: {list(self.encoders['academic_stage'].classes_)}")

            if stage == "FIRST_YEAR":
                qtype_raw = str(raw.get("qualification_type", "HSC_12TH")).strip().upper()
                if qtype_raw == "HSC":
                    qtype = "HSC_12TH"
                elif qtype_raw in ("HSC_12TH", "DIPLOMA", "OTHER"):
                    qtype = qtype_raw
                else:
                    raise ValueError(f"Invalid qualification_type: '{qtype_raw}' for FIRST_YEAR. Supported: HSC_12TH, DIPLOMA, OTHER")
            else:
                qtype = "NOT_APPLICABLE"

            score_val = (
                raw.get("academic_score")
                or raw.get("qualifying_score")
                or raw.get("first_year_score")
                or raw.get("second_year_score")
                or raw.get("third_year_score")
                or raw.get("ug_score")
            )
            if score_val is None:
                raise ValueError("Missing required field: academic_score")
            acad_score = float(score_val)

            prev_val = (
                raw.get("previous_score")
                or raw.get("ssc_score")
                or raw.get("qualifying_score")
                or raw.get("first_year_score")
                or raw.get("second_year_score")
                or acad_score
            )
            prev_score = float(prev_val)

            att_raw = raw.get("attendance")
            if stage == "FIRST_YEAR" or att_raw is None or str(att_raw).strip() in ("", "None", "nan"):
                attendance = np.nan
                is_att_app = 0
            else:
                attendance = float(att_raw)
                is_att_app = 1

            if "annual_income" not in raw:
                raise ValueError("Missing required field: annual_income")
            income = float(raw.get("annual_income", 300000.0))

            cat_raw = str(raw.get("application_category", "General")).strip()
            cat_norm = CANONICAL_CATEGORY_MAP.get(cat_raw.upper())
            if cat_norm is None:
                if cat_raw in self.encoders["application_category"].classes_:
                    cat_norm = cat_raw
                else:
                    raise ValueError(f"Invalid application_category: '{cat_raw}'. Supported canonical categories: {list(self.encoders['application_category'].classes_)}")

            sch_raw = str(raw.get("scholarship_scheme", "Merit Scholarship")).strip()
            sch_norm = SCHEME_NORMALIZATION_MAP.get(sch_raw) or SCHEME_NORMALIZATION_MAP.get(sch_raw.upper())
            if sch_norm is None:
                if sch_raw in self.encoders["scholarship_scheme"].classes_:
                    sch_norm = sch_raw
                else:
                    raise ValueError(f"Invalid scholarship_scheme: '{sch_raw}'. Supported: {list(self.encoders['scholarship_scheme'].classes_)}")

            docs_val = raw.get("documents_verified")
            caller_contract = raw.get("documents_verified_contract") or raw.get("caller_contract")
            docs_raw = normalize_document_status(docs_val, caller_contract=caller_contract)

            normalized = {
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

            for col in self.feature_cols:
                val = normalized[col]
                if col in self.categorical_cols:
                    le = self.encoders[col]
                    try:
                        row[col] = int(le.transform([str(val)])[0])
                    except Exception:
                        row[col] = 0
                else:
                    row[col] = float(val) if not np.isnan(val) else np.nan

            return pd.DataFrame([row])[self.feature_cols]

        else:
            # Legacy 7-feature encoding
            row = {}
            for col in self.feature_cols:
                if col not in raw:
                    raise ValueError(f"Missing required field: {col}")
                row[col] = raw[col]

            for col in self.categorical_cols:
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
                        # Fallback normalization
                        if col == "application_category":
                            val = CATEGORY_NORMALIZATION_MAP.get(str(val).upper(), "General")
                        elif col == "scholarship_scheme":
                            val = SCHEME_NORMALIZATION_MAP.get(str(val), "Merit Scholarship")
                        elif col == "documents_verified":
                            caller_contract = raw.get("documents_verified_contract") or raw.get("caller_contract")
                            val = normalize_document_status(val, caller_contract=caller_contract)

                row[col] = le.transform([val])[0]

            return pd.DataFrame([row])[self.feature_cols]

    def _shap_reasons(self, X: pd.DataFrame, class_idx: int, top_n: int = 3, raw_input: Optional[dict] = None) -> List[Dict[str, Any]]:
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
            # Check for fresh admission waived attendance
            if self.active_version == "stage_aware_v1" and feat == "attendance" and raw_input and (raw_input.get("academic_stage") == "FIRST_YEAR" or raw_input.get("attendance") is None):
                reasons.append({
                    "feature": feat,
                    "direction": "neutral",
                    "impact": 0.0,
                    "human_explanation": "College attendance is waived for fresh-admission applicants."
                })
            else:
                direction = "increased" if val > 0 else "decreased"
                disp_name = STAGE_AWARE_FEATURE_NAMES.get(feat, feat.replace("_", " ").title())
                reasons.append({
                    "feature": feat,
                    "direction": direction,
                    "impact": round(float(val), 3),
                    "human_explanation": f"{disp_name} had a {direction} influence on this assessment."
                })
        return reasons

    def predict_and_explain(self, raw_input: dict) -> dict:
        X = self._encode_input(raw_input)

        pred_encoded = int(self.model.predict(X)[0])
        proba = self.model.predict_proba(X)[0]
        model_decision = self.encoders["target"].inverse_transform([pred_encoded])[0]

        # Strict Gate 6 P(APPROVE) semantics
        prob_approve = float(proba[self.approve_idx])
        confidence = float(proba.max()) if self.active_version == "legacy_v2" else prob_approve

        reasons = self._shap_reasons(X, pred_encoded, top_n=3, raw_input=raw_input)

        # Apply hard override safety rules
        final_decision = model_decision
        override_applied = None

        doc_raw_val = raw_input.get("documents_verified")
        caller_contract = raw_input.get("documents_verified_contract") or raw_input.get("caller_contract")
        doc_status = normalize_document_status(doc_raw_val, caller_contract=caller_contract)

        if doc_status in BLOCKING_DOC_STATUSES and final_decision == "APPROVE":
            final_decision = "NEEDS_HUMAN_REVIEW"
            override_applied = "Blocked auto-approval: required documents incomplete."
        elif confidence < CONFIDENCE_THRESHOLD and final_decision != "NEEDS_HUMAN_REVIEW" and self.active_version == "legacy_v2":
            final_decision = "NEEDS_HUMAN_REVIEW"
            override_applied = (
                f"Model confidence ({confidence:.2f}) below threshold "
                f"({CONFIDENCE_THRESHOLD}) - routed to human review."
            )

        class_probabilities = {cls: round(float(p), 4) for cls, p in zip(self.classes, proba)}

        return {
            "model_decision": model_decision,
            "final_decision": final_decision,
            "decision": final_decision,
            "prediction": final_decision,
            "confidence": round(confidence, 4),
            "estimated_approval_probability": round(prob_approve, 4),
            "model_version": self.active_version,
            "class_probabilities": class_probabilities,
            "top_reasons": reasons,
            "override_applied": override_applied,
        }


# Singleton instance - loaded once when the Flask app starts
ml_service = MLService()


def set_active_version(version: str) -> None:
    ml_service.set_active_version(version)


def get_active_version() -> str:
    return ml_service.active_version
