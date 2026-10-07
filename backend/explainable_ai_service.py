"""
explainable_ai_service.py
--------------------------
Phase 1C: Interactive SHAP Explainability Service for JanNiti AI.

Explains why the trained Random Forest model (model_v2.pkl) produced
a specific administrative decision prediction (APPROVE, NEEDS_HUMAN_REVIEW, REJECT).

Key Guarantees:
1. Exact Feature Consistency:
   Reuses the exact 7-feature encoding pipeline and feature columns as ml_service.
2. Mathematically Grounded:
   Computes exact TreeSHAP values using shap.TreeExplainer on the pre-trained model.
   Guarantees TreeSHAP additivity: base_value + sum(shap_values) == predicted_proba.
3. Strict Separation of Concerns:
   SHAP values explain the ML model's internal statistical classification.
   Deterministic scholarship rules in Supabase govern authoritative eligibility.
4. Read-Only Safety:
   Zero persistent database mutations.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

try:
    from backend.ml_service import ml_service
    from backend.ml_application_service import (
        CATEGORY_ML_MAP,
        SCHOLARSHIP_SCHEME_ML_MAP,
    )
except ImportError:
    from ml_service import ml_service
    from ml_application_service import (
        CATEGORY_ML_MAP,
        SCHOLARSHIP_SCHEME_ML_MAP,
    )


FEATURE_DISPLAY_NAMES = {
    "academic_score": "Academic Score",
    "previous_score": "Previous Academic Score",
    "attendance": "Attendance Record",
    "annual_income": "Annual Family Income",
    "application_category": "Social Category",
    "scholarship_scheme": "Scholarship Scheme",
    "documents_verified": "Document Verification Status",
}

# Thresholds for SHAP direction and impact classification
DIRECTION_THRESHOLD = 0.005
HIGH_IMPACT_THRESHOLD = 0.15
MEDIUM_IMPACT_THRESHOLD = 0.05
LOW_IMPACT_THRESHOLD = 0.005


def format_feature_input_value(feature_name: str, value: Any) -> str:
    """Format raw input values into user-friendly strings for UI display."""
    if value is None:
        return "—"
    if feature_name in ("academic_score", "previous_score", "attendance"):
        try:
            return f"{float(value):.1f}%"
        except (ValueError, TypeError):
            return str(value)
    if feature_name == "annual_income":
        try:
            return f"₹{int(float(value)):,}"
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def _normalize_input_for_ml(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure input keys and values match the categorical classes expected by ml_service.
    Translates raw codes using authoritative mappings from ml_application_service.
    """
    normalized = dict(raw)

    valid_cats = set(ml_service.encoders["application_category"].classes_)
    valid_schemes = set(ml_service.encoders["scholarship_scheme"].classes_)
    valid_docs = set(ml_service.encoders["documents_verified"].classes_)

    # Normalize category
    cat = normalized.get("application_category") or normalized.get("category")
    if cat is not None:
        cat_str = str(cat).strip()
        if cat_str in valid_cats:
            normalized["application_category"] = cat_str
        elif cat_str.upper() in CATEGORY_ML_MAP:
            normalized["application_category"] = CATEGORY_ML_MAP[cat_str.upper()]
        elif cat_str.title() in valid_cats:
            normalized["application_category"] = cat_str.title()
        else:
            normalized["application_category"] = "General"
    else:
        normalized["application_category"] = "General"

    # Normalize scholarship scheme
    scheme = normalized.get("scholarship_scheme") or normalized.get("scheme_name") or normalized.get("scheme_code")
    if scheme is not None:
        sch_str = str(scheme).strip()
        if sch_str in valid_schemes:
            normalized["scholarship_scheme"] = sch_str
        elif sch_str in SCHOLARSHIP_SCHEME_ML_MAP:
            normalized["scholarship_scheme"] = SCHOLARSHIP_SCHEME_ML_MAP[sch_str]
        elif sch_str.upper() in SCHOLARSHIP_SCHEME_ML_MAP:
            normalized["scholarship_scheme"] = SCHOLARSHIP_SCHEME_ML_MAP[sch_str.upper()]
        else:
            normalized["scholarship_scheme"] = "Merit Scholarship"
    else:
        normalized["scholarship_scheme"] = "Merit Scholarship"

    # Normalize documents verified
    docs_status = normalized.get("documents_verified") or normalized.get("overall_status")
    if docs_status is not None:
        d_str = str(docs_status).strip().upper()
        if d_str in valid_docs:
            normalized["documents_verified"] = d_str
        elif d_str in ("MATCH", "TRUE", "COMPLETE", "YES"):
            normalized["documents_verified"] = "VERIFIED"
        else:
            normalized["documents_verified"] = "INCOMPLETE"
    else:
        normalized["documents_verified"] = "VERIFIED"

    return normalized


def _classify_direction(val: float) -> str:
    """Classify whether a SHAP value increases, decreases, or has neutral influence toward predicted class."""
    if val > DIRECTION_THRESHOLD:
        return "positive"
    if val < -DIRECTION_THRESHOLD:
        return "negative"
    return "neutral"


def _classify_impact(val: float) -> str:
    """Classify relative magnitude of a feature's SHAP contribution."""
    abs_val = abs(val)
    if abs_val >= HIGH_IMPACT_THRESHOLD:
        return "high"
    if abs_val >= MEDIUM_IMPACT_THRESHOLD:
        return "medium"
    if abs_val >= LOW_IMPACT_THRESHOLD:
        return "low"
    return "negligible"


def _build_feature_explanation(
    display_name: str,
    direction: str,
    class_name: str,
    shap_val: float,
    formatted_val: str,
) -> str:
    """
    Generate calibrated, non-overclaiming explanation sentences.
    Avoids causal overstatement (e.g. 'Because of X, you will get scholarship').
    """
    sign_str = f"+{shap_val:.2f}" if shap_val > 0 else f"{shap_val:.2f}"
    if direction == "positive":
        return (
            f"{display_name} ({formatted_val}) contributed positively toward "
            f"the model's {class_name} assessment (SHAP contribution: {sign_str})."
        )
    elif direction == "negative":
        return (
            f"{display_name} ({formatted_val}) exerted downward influence against "
            f"the model's {class_name} assessment (SHAP contribution: {sign_str})."
        )
    else:
        return (
            f"{display_name} ({formatted_val}) had a negligible influence on "
            f"the model's {class_name} assessment (SHAP contribution: {sign_str})."
        )


def _build_summary_text(features: List[Dict[str, Any]], class_name: str) -> str:
    """Synthesize high-level overview of the most impactful model factors."""
    positives = [f for f in features if f["direction"] == "positive"]
    negatives = [f for f in features if f["direction"] == "negative"]

    sentences: List[str] = []

    if positives:
        top_pos = positives[0]["display_name"]
        if len(positives) > 1 and positives[1]["impact"] in ("high", "medium"):
            sentences.append(
                f"{top_pos} and {positives[1]['display_name']} were the strongest positive "
                f"drivers toward the model's {class_name} assessment"
            )
        else:
            sentences.append(
                f"{top_pos} was the primary factor driving the model toward the {class_name} assessment"
            )

    if negatives:
        top_neg = negatives[0]["display_name"]
        sentences.append(
            f"{top_neg} exerted downward pressure against this assessment"
        )

    if not sentences:
        return (
            f"The model's assessment ({class_name}) was guided by the baseline historical "
            f"prior, with balanced contributions across all metrics."
        )

    return ". ".join(sentences) + "."


def generate_shap_explanation(
    raw_input: Dict[str, Any],
    class_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate interactive, structured SHAP explanation for a given student profile.

    Args:
        raw_input: Dictionary with student metrics and scheme context.
                   Keys: academic_score, previous_score, attendance, annual_income,
                         application_category, scholarship_scheme, documents_verified.
        class_override: Optional target class name to explain (APPROVE, NEEDS_HUMAN_REVIEW, REJECT).
                        Defaults to the model's top predicted class.

    Returns:
        Structured dictionary conforming to the Phase 1C explainability specification.
    """
    try:
        normalized = _normalize_input_for_ml(raw_input)

        # 1. Exact Feature Consistency via ml_service._encode_input
        X = ml_service._encode_input(normalized)

        # 2. Model Prediction & Probabilities
        proba = ml_service.model.predict_proba(X)[0]
        pred_encoded = ml_service.model.predict(X)[0]
        classes = list(ml_service.encoders["target"].classes_)
        predicted_class = classes[pred_encoded]

        # Determine target class for explanation
        if class_override and class_override in classes:
            target_class = class_override
            target_class_idx = classes.index(class_override)
        else:
            target_class = predicted_class
            target_class_idx = int(pred_encoded)

        confidence = float(proba[target_class_idx])
        confidence_display = f"{confidence * 100:.2f}%"

        # 3. Compute SHAP Values via singleton TreeExplainer
        shap_values = ml_service.explainer.shap_values(X)

        if isinstance(shap_values, list):
            class_shap = shap_values[target_class_idx][0]
            base_value = float(ml_service.explainer.expected_value[target_class_idx])
        else:
            class_shap = shap_values[0, :, target_class_idx]
            base_value = float(ml_service.explainer.expected_value[target_class_idx])

        # 4. Map SHAP values to 7 features with human-readable metadata
        features: List[Dict[str, Any]] = []
        for i, feat_name in enumerate(ml_service.feature_cols):
            shap_val = float(class_shap[i])
            display_name = FEATURE_DISPLAY_NAMES.get(feat_name, feat_name.replace("_", " ").title())
            raw_val = normalized.get(feat_name)
            formatted_val = format_feature_input_value(feat_name, raw_val)

            direction = _classify_direction(shap_val)
            impact = _classify_impact(shap_val)
            explanation = _build_feature_explanation(display_name, direction, target_class, shap_val, formatted_val)

            features.append({
                "feature": feat_name,
                "display_name": display_name,
                "input_value": raw_val,
                "formatted_input": formatted_val,
                "shap_value": round(shap_val, 4),
                "shap_display": f"+{shap_val:.2f}" if shap_val > 0 else f"{shap_val:.2f}",
                "direction": direction,
                "impact": impact,
                "explanation": explanation,
            })

        # 5. Rank features strictly by absolute SHAP magnitude (highest impact first)
        features.sort(key=lambda f: abs(f["shap_value"]), reverse=True)

        positive_factors = [f for f in features if f["direction"] == "positive"]
        negative_factors = [f for f in features if f["direction"] == "negative"]
        neutral_factors = [f for f in features if f["direction"] == "neutral"]

        summary_text = _build_summary_text(features, target_class)

        return {
            "status": "success",
            "prediction": {
                "class": target_class,
                "predicted_class": predicted_class,
                "confidence": round(confidence, 4),
                "confidence_display": confidence_display,
            },
            "explanation": {
                "base_value": round(base_value, 4),
                "output_class": target_class,
                "features": features,
                "positive_factors": positive_factors,
                "negative_factors": negative_factors,
                "neutral_factors": neutral_factors,
                "summary_text": summary_text,
                "disclaimer": (
                    "SHAP values explain the machine learning model's statistical decision "
                    "weights based on historical training data. Authoritative scholarship "
                    "eligibility is governed independently by deterministic scheme rules."
                ),
            },
        }

    except Exception as exc:
        return {
            "status": "unavailable",
            "error": "AI prediction is available, but detailed explanation could not be generated.",
            "details": str(exc),
            "prediction": None,
            "explanation": None,
        }
