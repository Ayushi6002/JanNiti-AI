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

CATEGORY_ML_MAP = {
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

    # Normalize category for ML encoder
    category_raw = str(application.get("application_category", "")).strip().upper()
    category_mapped = CATEGORY_ML_MAP.get(category_raw)
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

    ml_input = {
        "academic_score": float(application["academic_score"]),
        "previous_score": float(application["previous_score"]),
        "attendance": float(application["attendance"]),
        "annual_income": float(application["annual_income"]),
        "application_category": category_mapped,
        "scholarship_scheme": scheme_mapped,
        "documents_verified": documents_verified,
    }

    prediction = ml_service.predict_and_explain(ml_input)

    return {
        "application_id": application_id,
        "ml_input": ml_input,
        "prediction": prediction,
    }