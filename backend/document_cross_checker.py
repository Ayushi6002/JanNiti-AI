import re
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any

try:
    from backend.document_extractor import normalize_category
except ImportError:
    from document_extractor import normalize_category


def _parse_date(date_str: str) -> Optional[date]:
    """Parse various date formats (YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY)."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    patterns = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]
    for p in patterns:
        try:
            return datetime.strptime(date_str, p).date()
        except ValueError:
            continue
    return None


def compare_marksheet_with_application(
    extracted_data: dict,
    application_data: dict
) -> dict:

    field_results = {}

    # Academic score
    document_score = extracted_data.get("academic_score")
    application_score = application_data.get("academic_score")

    if document_score is None:
        field_results["academic_score"] = {
            "status": "MISSING",
            "document_value": None,
            "application_value": application_score
        }

    elif application_score is None:
        field_results["academic_score"] = {
            "status": "MISSING_APPLICATION_VALUE",
            "document_value": document_score,
            "application_value": None
        }

    elif abs(document_score - application_score) <= 0.01:
        field_results["academic_score"] = {
            "status": "MATCH",
            "document_value": document_score,
            "application_value": application_score
        }

    else:
        field_results["academic_score"] = {
            "status": "MISMATCH",
            "document_value": document_score,
            "application_value": application_score
        }

    # Previous score
    document_previous = extracted_data.get("previous_score")
    application_previous = application_data.get("previous_score")

    if document_previous is None:
        field_results["previous_score"] = {
            "status": "MISSING",
            "document_value": None,
            "application_value": application_previous
        }

    elif application_previous is None:
        field_results["previous_score"] = {
            "status": "MISSING_APPLICATION_VALUE",
            "document_value": document_previous,
            "application_value": None
        }

    elif abs(document_previous - application_previous) <= 0.01:
        field_results["previous_score"] = {
            "status": "MATCH",
            "document_value": document_previous,
            "application_value": application_previous
        }

    else:
        field_results["previous_score"] = {
            "status": "MISMATCH",
            "document_value": document_previous,
            "application_value": application_previous
        }

    statuses = [
        result["status"]
        for result in field_results.values()
    ]

    if "MISMATCH" in statuses:
        overall_status = "MISMATCH"
    elif "MISSING" in statuses:
        overall_status = "NEEDS_REVIEW"
    elif "MISSING_APPLICATION_VALUE" in statuses:
        overall_status = "NEEDS_REVIEW"
    else:
        overall_status = "MATCH"

    return {
        "overall_status": overall_status,
        "fields": field_results
    }

def compare_income_certificate_with_application(
    extracted_data,
    application_data
):
    field_results = {}

    document_income = extracted_data.get("annual_income")
    application_income = application_data.get("annual_income")

    if document_income is None:
        field_results["annual_income"] = {
            "status": "MISSING",
            "document_value": None,
            "application_value": application_income
        }

    elif application_income is None:
        field_results["annual_income"] = {
            "status": "MISSING_APPLICATION_VALUE",
            "document_value": document_income,
            "application_value": None
        }

    elif abs(document_income - application_income) < 0.01:
        field_results["annual_income"] = {
            "status": "MATCH",
            "document_value": document_income,
            "application_value": application_income
        }

    else:
        field_results["annual_income"] = {
            "status": "MISMATCH",
            "document_value": document_income,
            "application_value": application_income
        }

    statuses = [
        result["status"]
        for result in field_results.values()
    ]

    if "MISMATCH" in statuses:
        overall_status = "MISMATCH"
    elif "MISSING" in statuses:
        overall_status = "NEEDS_REVIEW"
    elif "MISSING_APPLICATION_VALUE" in statuses:
        overall_status = "NEEDS_REVIEW"
    else:
        overall_status = "MATCH"

    return {
        "overall_status": overall_status,
        "fields": field_results
    }
def compare_id_proof_with_profile(
    extracted_data,
    profile_data
):
    field_results = {}

    document_name = extracted_data.get("student_name")
    profile_name = profile_data.get("full_name")

    if document_name is None:
        field_results["student_name"] = {
            "status": "MISSING",
            "document_value": None,
            "profile_value": profile_name
        }

    elif profile_name is None:
        field_results["student_name"] = {
            "status": "MISSING_PROFILE_VALUE",
            "document_value": document_name,
            "profile_value": None
        }

    elif document_name.strip().lower() == profile_name.strip().lower():
        field_results["student_name"] = {
            "status": "MATCH",
            "document_value": document_name,
            "profile_value": profile_name
        }

    else:
        field_results["student_name"] = {
            "status": "MISMATCH",
            "document_value": document_name,
            "profile_value": profile_name
        }

    statuses = [
        result["status"]
        for result in field_results.values()
    ]

    if "MISMATCH" in statuses:
        overall_status = "MISMATCH"

    elif "MISSING" in statuses:
        overall_status = "NEEDS_REVIEW"

    elif "MISSING_PROFILE_VALUE" in statuses:
        overall_status = "NEEDS_REVIEW"

    else:
        overall_status = "MATCH"

    return {
        "overall_status": overall_status,
        "fields": field_results
    }


def compare_category_certificate_with_application(
    extracted_data: dict,
    application_data: dict,
    profile_data: Optional[dict] = None
) -> dict:
    """
    Transparently verify Category Certificate against application & profile.
    Checks:
      1. Category match (with normalization across SC, ST, OBC, EWS, GENERAL)
      2. Student name verification against applicant profile
      3. Certificate validity (expiry date, future issue date, malformed dates)

    Returns comprehensive verification dictionary.
    """
    # 1. Category Check
    doc_cat_raw = extracted_data.get("category")
    app_cat_raw = application_data.get("application_category")

    doc_cat_norm = extracted_data.get("normalized_category") or normalize_category(doc_cat_raw)
    app_cat_norm = normalize_category(app_cat_raw)

    if doc_cat_raw is None:
        category_check = {
            "status": "MISSING",
            "application_category": app_cat_raw,
            "document_category": None,
            "reason": "Category not found in category certificate."
        }
    elif app_cat_raw is None:
        category_check = {
            "status": "MISSING",
            "application_category": None,
            "document_category": doc_cat_raw,
            "reason": "Declared application category is missing."
        }
    elif doc_cat_norm is None or app_cat_norm is None:
        category_check = {
            "status": "UNCERTAIN",
            "application_category": app_cat_raw,
            "document_category": doc_cat_raw,
            "reason": "Unable to reliably normalize category."
        }
    elif doc_cat_norm == app_cat_norm:
        category_check = {
            "status": "MATCH",
            "application_category": app_cat_raw,
            "document_category": doc_cat_raw,
            "normalized_category": doc_cat_norm,
            "reason": "Declared category matches the category certificate."
        }
    else:
        category_check = {
            "status": "MISMATCH",
            "application_category": app_cat_raw,
            "document_category": doc_cat_raw,
            "normalized_application_category": app_cat_norm,
            "normalized_document_category": doc_cat_norm,
            "reason": "Declared category does not match the category certificate."
        }

    # 2. Name Check
    doc_name = extracted_data.get("student_name")
    profile_name = None
    if profile_data and isinstance(profile_data, dict):
        profile_name = profile_data.get("full_name")
    if not profile_name:
        profile_name = application_data.get("full_name") or application_data.get("applicant_name")

    if not doc_name or not str(doc_name).strip():
        name_check = {
            "status": "NOT_AVAILABLE",
            "document_name": None,
            "profile_name": profile_name,
            "reason": "Student name not available on category certificate."
        }
    elif not profile_name or not str(profile_name).strip():
        name_check = {
            "status": "NOT_AVAILABLE",
            "document_name": doc_name,
            "profile_name": None,
            "reason": "Applicant profile name not available for cross-check."
        }
    elif str(doc_name).strip().lower() == str(profile_name).strip().lower():
        name_check = {
            "status": "MATCH",
            "document_name": doc_name,
            "profile_name": profile_name,
            "reason": "Applicant name matches category certificate."
        }
    else:
        name_check = {
            "status": "MISMATCH",
            "document_name": doc_name,
            "profile_name": profile_name,
            "reason": f"Declared name ('{profile_name}') does not match certificate name ('{doc_name}')."
        }

    # 3. Validity / Temporal Check
    issue_date_str = extracted_data.get("issue_date")
    expiry_date_str = extracted_data.get("expiry_date")
    today = datetime.now(timezone.utc).date()

    if not issue_date_str and not expiry_date_str:
        validity_check = {
            "status": "NOT_AVAILABLE",
            "issue_date": None,
            "expiry_date": None,
            "reason": "No issue or expiry date specified on certificate."
        }
    else:
        parsed_issue = _parse_date(issue_date_str) if issue_date_str else None
        parsed_expiry = _parse_date(expiry_date_str) if expiry_date_str else None

        if issue_date_str and not parsed_issue:
            validity_check = {
                "status": "MALFORMED",
                "issue_date": issue_date_str,
                "expiry_date": expiry_date_str,
                "reason": f"Malformed issue date format: '{issue_date_str}'."
            }
        elif expiry_date_str and not parsed_expiry:
            validity_check = {
                "status": "MALFORMED",
                "issue_date": issue_date_str,
                "expiry_date": expiry_date_str,
                "reason": f"Malformed expiry date format: '{expiry_date_str}'."
            }
        elif parsed_issue and parsed_issue > today:
            validity_check = {
                "status": "FUTURE_DATE",
                "issue_date": str(parsed_issue),
                "expiry_date": str(parsed_expiry) if parsed_expiry else None,
                "reason": f"Certificate has an impossible future issue date ({parsed_issue})."
            }
        elif parsed_expiry and parsed_expiry < today:
            validity_check = {
                "status": "EXPIRED",
                "issue_date": str(parsed_issue) if parsed_issue else None,
                "expiry_date": str(parsed_expiry),
                "reason": f"Certificate expired on {parsed_expiry}."
            }
        else:
            validity_check = {
                "status": "VALID",
                "issue_date": str(parsed_issue) if parsed_issue else None,
                "expiry_date": str(parsed_expiry) if parsed_expiry else None,
                "reason": "Certificate dates are valid."
            }

    # 4. Overall status determination
    if category_check["status"] == "MISMATCH":
        overall_status = "MISMATCH"
        verification_status = "MISMATCH"
        verification_score = 0.0
    elif name_check["status"] == "MISMATCH":
        overall_status = "MISMATCH"
        verification_status = "MISMATCH"
        verification_score = 50.0
    elif validity_check["status"] in ("EXPIRED", "FUTURE_DATE"):
        overall_status = "MISMATCH"
        verification_status = "MISMATCH"
        verification_score = 50.0
    elif category_check["status"] == "MISSING":
        overall_status = "INCOMPLETE"
        verification_status = "NEEDS_REVIEW"
        verification_score = 0.0
    elif category_check["status"] == "UNCERTAIN" or validity_check["status"] == "MALFORMED":
        overall_status = "UNCERTAIN"
        verification_status = "NEEDS_REVIEW"
        verification_score = 50.0
    else:
        # Category MATCH, name MATCH or NOT_AVAILABLE, validity VALID or NOT_AVAILABLE
        overall_status = "MATCH"
        verification_status = "VERIFIED"
        verification_score = 100.0

    # 5. Build fields dict for backward compatibility
    field_results = {
        "category": {
            "status": category_check["status"],
            "document_value": doc_cat_raw,
            "application_value": app_cat_raw,
            "reason": category_check["reason"]
        },
        "student_name": {
            "status": name_check["status"],
            "document_value": doc_name,
            "profile_value": profile_name,
            "reason": name_check["reason"]
        },
        "validity": {
            "status": validity_check["status"],
            "issue_date": validity_check.get("issue_date"),
            "expiry_date": validity_check.get("expiry_date"),
            "reason": validity_check["reason"]
        }
    }

    return {
        "document_type": "category_certificate",
        "verification_status": verification_status,
        "verification_score": verification_score,
        "overall_status": overall_status,
        "category_check": category_check,
        "name_check": name_check,
        "validity_check": validity_check,
        "fields": field_results
    }