try:
    from backend.application_service import (
        get_application_verification_data,
    )
    from backend.verification_service import generate_verification_summary
    from backend.supabase_client import supabase
    from backend.ml_service import ml_service
except ImportError:
    from application_service import (
        get_application_verification_data,
    )
    from verification_service import generate_verification_summary
    from supabase_client import supabase
    from ml_service import ml_service


SCHOLARSHIP_SCHEME_ML_MAP = {
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

# Canonical Social Categories for Stage 2D.1 Remediated Candidate Model
# Strictly preserves distinct constitutional groups: General, OBC, SC, ST, EWS
CANONICAL_CATEGORY_ML_MAP = {
    "GENERAL": "General",
    "GEN": "General",
    "OPEN": "General",
    "UNRESERVED": "General",
    "UR": "General",
    "OBC": "OBC",
    "OTHER BACKWARD CLASS": "OBC",
    "OTHER BACKWARD CLASSES": "OBC",
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
    "MERIT": "General",
    "SPECIAL CIRCUMSTANCE": "General",
    "SPECIAL_CIRCUMSTANCE": "General",
    "CATEGORY": "General",
}

# Legacy Adapter Map (Used exclusively when running legacy_v2 model)
LEGACY_CATEGORY_ML_MAP = {
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

CATEGORY_ML_MAP = LEGACY_CATEGORY_ML_MAP


def get_application_for_ml(application_id: str):
    """
    Fetch the application data required by the ML model.
    """

    application = get_application_verification_data(application_id)

    if not application:
        raise ValueError(f"Application not found: {application_id}")

    # Fetch scholarship scheme name
    response = (
        supabase
        .table("applications")
        .select("""
            scholarship_scheme_id,
            scholarship_schemes (
                scheme_code,
                scheme_name
            )
        """)
        .eq("id", application_id)
        .single()
        .execute()
    )

    data = response.data

    if not data:
        raise ValueError(
            f"Scholarship scheme not found for application: {application_id}"
        )

    scheme = data.get("scholarship_schemes")

    if not scheme:
        raise ValueError(
            f"Scholarship scheme details missing for application: {application_id}"
        )

    application["scholarship_scheme"] = scheme["scheme_name"]
    application["scholarship_scheme_code"] = scheme.get("scheme_code")

    return application


def get_document_status_for_ml(application_id: str):
    """
    Convert the application verification summary into
    the document status expected by the ML model.
    """

    summary = generate_verification_summary(application_id)

    overall_status = summary["overall_status"]

    if overall_status == "VERIFIED":
        return "VERIFIED"

    if overall_status == "INCOMPLETE":
        return "INCOMPLETE"

    # ML training data uses UNCERTAIN for cases that
    # cannot safely be treated as verified.
    return "UNCERTAIN"


def predict_application(application_id: str):
    """
    Run ML prediction for a real Supabase application.
    """

    application = get_application_for_ml(application_id)

    documents_verified = get_document_status_for_ml(application_id)

    # Normalize category for ML encoder based on active model version
    category_raw = str(application.get("application_category", "")).strip().upper()
    if ml_service.active_version == "stage_aware_v1":
        category_mapped = CANONICAL_CATEGORY_ML_MAP.get(category_raw, "General")
        if category_mapped not in ml_service.encoders["application_category"].classes_:
            category_mapped = "General"
    else:
        category_mapped = LEGACY_CATEGORY_ML_MAP.get(category_raw)
        if not category_mapped:
            cat_title = category_raw.replace("_", " ").title()
            if cat_title in ml_service.encoders["application_category"].classes_:
                category_mapped = cat_title
            else:
                category_mapped = "General"

    # Normalize scheme for ML encoder
    scheme_raw = str(application.get("scholarship_scheme", "")).strip()
    scheme_code = str(application.get("scholarship_scheme_code", "")).strip().upper()
    scheme_mapped = SCHOLARSHIP_SCHEME_ML_MAP.get(scheme_raw) or SCHOLARSHIP_SCHEME_ML_MAP.get(scheme_code)
    if not scheme_mapped:
        scheme_mapped = "Merit Scholarship"
    # Check model version capability for first-year / waived attendance
    if ml_service.active_version == "stage_aware_v1":
        stage = application.get("academic_stage") or ("FIRST_YEAR" if application.get("attendance") is None else "SECOND_YEAR")
        qtype = application.get("qualification_type") or ("HSC_12TH" if application.get("attendance") is None else "NOT_APPLICABLE")
        has_attendance = application.get("attendance") is not None and str(application.get("attendance")).strip() not in ("", "None", "nan")
        att_val = float(application["attendance"]) if has_attendance else None

        ml_input = {
            "academic_stage": stage,
            "qualification_type": qtype,
            "academic_score": float(application["academic_score"]),
            "previous_score": float(application["previous_score"]),
            "attendance": att_val,
            "is_attendance_applicable": 1 if has_attendance else 0,
            "annual_income": float(application["annual_income"]),
            "application_category": category_mapped,
            "scholarship_scheme": scheme_mapped,
            "documents_verified": documents_verified,
            "documents_verified_contract": "VERIFIED_SERVICE",
        }

        prediction = ml_service.predict_and_explain(ml_input)

        return {
            "application_id": application_id,
            "ml_input": ml_input,
            "prediction": prediction,
        }

    # Legacy model (7 features) behavior:
    # Requires attendance; when NULL (e.g. fresh admissions), routes safely to Human Review guardrail
    if application.get("attendance") is None:
        prediction = {
            "prediction": "NEEDS_HUMAN_REVIEW",
            "decision": "NEEDS_HUMAN_REVIEW",
            "probability": None,
            "confidence": None,
            "estimated_approval_probability": None,
            "risk_level": "LOW",
            "model_version": "v2_stage_aware_guardrail",
            "explanation": {
                "message": (
                    "Attendance is not applicable for fresh admission applicants (waived). "
                    "The current 7-feature model does not evaluate fresh admissions; routed to Human Review."
                ),
                "why_approved": [],
                "why_rejected": [],
                "readable_reasons": [
                    "Fresh admission applicant with waived attendance record routed directly to human evaluation."
                ],
                "feature_breakdown": [],
            },
            "top_reasons": [
                {
                    "feature": "attendance",
                    "direction": "neutral",
                    "impact": 0.0,
                    "human_explanation": "Attendance is waived for fresh admission applicants."
                }
            ],
            "feature_breakdown": [],
        }
        return {
            "application_id": application_id,
            "ml_input": {
                "academic_score": float(application["academic_score"]),
                "previous_score": float(application["previous_score"]),
                "attendance": None,
                "annual_income": float(application["annual_income"]),
                "application_category": category_mapped,
                "scholarship_scheme": scheme_mapped,
                "documents_verified": documents_verified,
            },
            "prediction": prediction,
        }

    ml_input = {
        "academic_score": float(application["academic_score"]),
        "previous_score": float(application["previous_score"]),
        "attendance": float(application["attendance"]),
        "annual_income": float(application["annual_income"]),
        "application_category": category_mapped,
        "scholarship_scheme": scheme_mapped,
        "documents_verified": documents_verified,
        "documents_verified_contract": "VERIFIED_SERVICE",
    }

    prediction = ml_service.predict_and_explain(ml_input)

    return {
        "application_id": application_id,
        "ml_input": ml_input,
        "prediction": prediction,
    }