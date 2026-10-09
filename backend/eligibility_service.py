try:
    from backend.supabase_client import supabase
    from backend.application_service import (
        get_application_verification_data,
        get_applicant_profile
    )
    from backend.verification_service import generate_verification_summary
except ImportError:
    from supabase_client import supabase
    from application_service import (
        get_application_verification_data,
        get_applicant_profile
    )
    from verification_service import generate_verification_summary



def get_scholarship_rules(scholarship_scheme_id: str):
    """
    Fetch active eligibility rules for a scholarship scheme.
    """

    response = (
        supabase
        .table("scholarship_rules")
        .select(
            """
            id,
            rule_code,
            rule_name,
            rule_type,
            rule_config,
            is_active
            """
        )
        .eq("scholarship_scheme_id", scholarship_scheme_id)
        .eq("is_active", True)
        .order("rule_code")
        .execute()
    )

    return response.data or []


def evaluate_min_value(rule, application_data):
    """
    Evaluate rules such as:
    academic_score >= 75
    attendance >= 75
    """

    config = rule["rule_config"]

    field = config["field"]
    minimum = float(config["minimum"])

    actual_value = application_data.get(field)

    if actual_value is None:
        # For fresh-admission first-year students, college attendance is genuinely not applicable / waived
        if field == "attendance":
            return {
                "status": "PASS",
                "message": "College attendance requirement is not applicable (waived for fresh admission).",
                "actual_value": None,
                "required_value": minimum,
                "waived": True,
            }
        return {
            "status": "FAIL",
            "message": f"{field} is missing.",
            "actual_value": None,
            "required_value": minimum
        }

    actual_value = float(actual_value)

    passed = actual_value >= minimum

    return {
        "status": "PASS" if passed else "FAIL",
        "message": (
            f"{field} is {actual_value}, "
            f"required minimum is {minimum}."
        ),
        "actual_value": actual_value,
        "required_value": minimum
    }


def evaluate_max_value(rule, application_data):
    """
    Evaluate rules such as:
    annual_income <= 800000
    """

    config = rule["rule_config"]

    field = config["field"]
    maximum = float(config["maximum"])

    actual_value = application_data.get(field)

    if actual_value is None:
        return {
            "status": "FAIL",
            "message": f"{field} is missing.",
            "actual_value": None,
            "required_value": maximum
        }

    actual_value = float(actual_value)

    passed = actual_value <= maximum

    return {
        "status": "PASS" if passed else "FAIL",
        "message": (
            f"{field} is {actual_value}, "
            f"maximum allowed is {maximum}."
        ),
        "actual_value": actual_value,
        "required_value": maximum
    }


def evaluate_document_verification(
    rule,
    verification_summary
):
    """
    Check whether all required documents are verified.
    """

    required_documents = verification_summary["required_documents"]

    verified_documents = []

    for document_type in required_documents:

        document_data = verification_summary["documents"].get(
            document_type
        )

        if document_data:
            status = document_data["status"]

            if status == "VERIFIED":
                verified_documents.append(document_type)

    passed = len(verified_documents) == len(required_documents)

    return {
        "status": "PASS" if passed else "FAIL",
        "message": (
            "All required documents are verified."
            if passed
            else "One or more required documents are not verified."
        ),
        "verified_documents": verified_documents,
        "required_documents": required_documents
    }


def evaluate_rule(rule, application_data, verification_summary):
    """
    Evaluate one rule according to its rule type.
    """

    rule_type = rule["rule_type"]

    if rule_type == "MIN_VALUE":
        return evaluate_min_value(
            rule,
            application_data
        )

    if rule_type == "MAX_VALUE":
        return evaluate_max_value(
            rule,
            application_data
        )

    if rule_type == "DOCUMENT_VERIFICATION":
        return evaluate_document_verification(
            rule,
            verification_summary
        )

    return {
        "status": "FAIL",
        "message": f"Unsupported rule type: {rule_type}"
    }


def evaluate_application_eligibility(
    application_id: str,
    scholarship_scheme_id: str
):
    """
    Evaluate all eligibility rules for an application.
    """

    application_data = get_application_verification_data(
        application_id
    )

    if not application_data:
        raise ValueError("Application not found.")

    verification_summary = generate_verification_summary(
        application_id
    )

    rules = get_scholarship_rules(
        scholarship_scheme_id
    )

    if not rules:
        raise ValueError(
            "No active eligibility rules found."
        )

    return evaluate_rules_for_data(
        rules=rules,
        application_data=application_data,
        verification_summary=verification_summary,
        application_id=application_id,
        scholarship_scheme_id=scholarship_scheme_id,
    )


def evaluate_rules_for_data(
    rules: list,
    application_data: dict,
    verification_summary: dict,
    application_id: str = None,
    scholarship_scheme_id: str = None,
) -> dict:
    """
    Evaluate a set of scholarship rules against given application data and
    verification summary. Used by both the live pipeline and the simulation engine.
    """
    rule_results = []
    passed_rules = []
    failed_rules = []

    for rule in rules:
        result = evaluate_rule(
            rule,
            application_data,
            verification_summary
        )

        rule_result = {
            "rule_code": rule["rule_code"],
            "rule_name": rule["rule_name"],
            "rule_type": rule["rule_type"],
            "status": result["status"],
            "message": result["message"],
            "details": result,
            "rule_config": rule.get("rule_config"),
        }

        rule_results.append(rule_result)

        if result["status"] == "PASS":
            passed_rules.append(rule_result)
        else:
            failed_rules.append(rule_result)

    eligible = len(failed_rules) == 0

    return {
        "application_id": application_id,
        "scholarship_scheme_id": scholarship_scheme_id,
        "eligible": eligible,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "total_rules": len(rule_results),
        "passed_count": len(passed_rules),
        "failed_count": len(failed_rules),
    }