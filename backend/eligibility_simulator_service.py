"""
eligibility_simulator_service.py
--------------------------------
Service for simulating "what-if" eligibility changes on scholarship applications.
Guarantees read-only execution: no database rows, documents, predictions,
decisions, or audit logs are ever modified or created.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.supabase_client import supabase
    from backend.application_service import get_application_verification_data
    from backend.verification_service import generate_verification_summary
    from backend.eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )
except ImportError:
    from supabase_client import supabase
    from application_service import get_application_verification_data
    from verification_service import generate_verification_summary
    from eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )


try:
    from backend.passport_service import ApplicationNotFoundError
except ImportError:
    try:
        from passport_service import ApplicationNotFoundError
    except ImportError:
        class ApplicationNotFoundError(Exception):
            """Raised when the specified application does not exist."""
            pass


class ForbiddenSimulationAccessError(Exception):
    """Raised when an applicant attempts to simulate another applicant's application."""
    pass


# Only existing numeric criteria and application category are valid overrides.
ALLOWED_OVERRIDE_FIELDS = {
    "academic_score",
    "previous_score",
    "attendance",
    "annual_income",
    "application_category",
}

NUMERIC_FIELDS = {
    "academic_score",
    "previous_score",
    "attendance",
    "annual_income",
}


def validate_simulation_overrides(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate simulation override keys and values.
    Returns cleaned dictionary with float-converted numeric values.
    Raises ValueError with descriptive message if validation fails.
    """
    if not isinstance(overrides, dict):
        raise ValueError("Simulation overrides must be provided as a JSON object.")

    cleaned: Dict[str, Any] = {}

    for field, val in overrides.items():
        if field not in ALLOWED_OVERRIDE_FIELDS:
            raise ValueError(
                f"Invalid override field '{field}'. Allowed fields: {sorted(ALLOWED_OVERRIDE_FIELDS)}"
            )

        if val is None:
            raise ValueError(f"Override value for '{field}' cannot be null.")

        if field in {"academic_score", "previous_score", "attendance"}:
            try:
                num_val = float(val)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"'{field}' must be a valid numeric score.") from exc

            if not (0 <= num_val <= 100):
                raise ValueError(f"'{field}' must be between 0 and 100.")

            cleaned[field] = num_val

        elif field == "annual_income":
            try:
                num_val = float(val)
            except (ValueError, TypeError) as exc:
                raise ValueError("'annual_income' must be a valid numeric value.") from exc

            if num_val < 0:
                raise ValueError("'annual_income' cannot be negative.")

            cleaned[field] = num_val

        elif field == "application_category":
            str_val = str(val).strip().upper()
            if not str_val:
                raise ValueError("'application_category' cannot be empty.")
            cleaned[field] = str_val

    return cleaned


def analyze_rule_requirements(
    rules: List[Dict[str, Any]],
    application_data: Dict[str, Any],
    verification_summary: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Analyzes each rule requirement against the application's actual data to determine:
    1. Full requirements analysis (current value, required value, gap, direction, status).
    2. Recommended changes (closest minimum changes needed to satisfy failed numeric rules).
    """
    requirements_analysis: List[Dict[str, Any]] = []
    recommended_changes: List[Dict[str, Any]] = []

    for rule in rules:
        rtype = rule.get("rule_type")
        rcode = rule.get("rule_code")
        rname = rule.get("rule_name")
        rconfig = rule.get("rule_config") or {}

        if rtype == "MIN_VALUE":
            field = rconfig.get("field")
            minimum = float(rconfig.get("minimum", 0))
            current_raw = application_data.get(field)
            current_val = float(current_raw) if current_raw is not None else 0.0
            satisfied = current_val >= minimum
            gap = round(max(0.0, minimum - current_val), 2)
            direction = "INCREASE" if not satisfied else None

            if satisfied:
                msg = f"{field.replace('_', ' ').capitalize()} satisfies the minimum requirement of at least {minimum}."
            else:
                msg = (
                    f"To satisfy {rname}, the simulated {field.replace('_', ' ')} "
                    f"would need to reach at least {minimum} (increase of {gap})."
                )

            analysis_item = {
                "rule": rcode,
                "rule_name": rname,
                "rule_type": rtype,
                "field": field,
                "current_value": current_val,
                "required_value": minimum,
                "gap": gap,
                "direction": direction,
                "satisfied": satisfied,
                "message": msg,
            }
            requirements_analysis.append(analysis_item)

            if not satisfied:
                recommended_changes.append({
                    "field": field,
                    "rule": rcode,
                    "rule_name": rname,
                    "current": current_val,
                    "target": minimum,
                    "gap": gap,
                    "direction": "INCREASE",
                    "message": (
                        f"To satisfy the current eligibility rules, the simulated {field.replace('_', ' ')} "
                        f"would need to reach {minimum} (increase of {gap})."
                    ),
                })

        elif rtype == "MAX_VALUE":
            field = rconfig.get("field")
            maximum = float(rconfig.get("maximum", 0))
            current_raw = application_data.get(field)
            current_val = float(current_raw) if current_raw is not None else 0.0
            satisfied = current_val <= maximum
            gap = round(max(0.0, current_val - maximum), 2)
            direction = "DECREASE" if not satisfied else None

            if satisfied:
                msg = f"{field.replace('_', ' ').capitalize()} satisfies the upper limit of at most {maximum}."
            else:
                msg = (
                    f"To satisfy {rname}, the simulated {field.replace('_', ' ')} "
                    f"would need to reach at most {maximum} (decrease of {gap})."
                )

            analysis_item = {
                "rule": rcode,
                "rule_name": rname,
                "rule_type": rtype,
                "field": field,
                "current_value": current_val,
                "required_value": maximum,
                "gap": gap,
                "direction": direction,
                "satisfied": satisfied,
                "message": msg,
            }
            requirements_analysis.append(analysis_item)

            if not satisfied:
                recommended_changes.append({
                    "field": field,
                    "rule": rcode,
                    "rule_name": rname,
                    "current": current_val,
                    "target": maximum,
                    "gap": gap,
                    "direction": "DECREASE",
                    "message": (
                        f"To satisfy the current eligibility rules, the simulated {field.replace('_', ' ')} "
                        f"would need to reach {maximum} (decrease of {gap})."
                    ),
                })

        elif rtype == "DOCUMENT_VERIFICATION":
            overall = verification_summary.get("overall_status")
            missing = verification_summary.get("missing_documents") or []
            mismatched = verification_summary.get("mismatched_documents") or []
            needs_review = verification_summary.get("needs_review_documents") or []

            satisfied = (
                overall == "VERIFIED"
                and len(missing) == 0
                and len(mismatched) == 0
                and len(needs_review) == 0
            )

            if satisfied:
                msg = "All required documents are verified."
            else:
                unmet_parts = []
                if missing:
                    unmet_parts.append(f"missing: {', '.join(missing)}")
                if mismatched:
                    unmet_parts.append(f"mismatched: {', '.join(mismatched)}")
                if needs_review:
                    unmet_parts.append(f"needs review: {', '.join(needs_review)}")
                detail_str = f" ({'; '.join(unmet_parts)})" if unmet_parts else ""
                msg = (
                    f"Document verification requirements are currently unmet{detail_str}. "
                    f"All required documents must be uploaded and verified in the database."
                )

            analysis_item = {
                "rule": rcode,
                "rule_name": rname,
                "rule_type": rtype,
                "field": "documents",
                "current_value": overall or "UNVERIFIED",
                "required_value": "VERIFIED",
                "gap": None,
                "direction": None,
                "satisfied": satisfied,
                "message": msg,
            }
            requirements_analysis.append(analysis_item)

            if not satisfied:
                recommended_changes.append({
                    "field": "documents",
                    "rule": rcode,
                    "rule_name": rname,
                    "current": overall or "UNVERIFIED",
                    "target": "VERIFIED",
                    "gap": None,
                    "direction": None,
                    "message": msg,
                })

    return requirements_analysis, recommended_changes


def simulate_eligibility(
    application_id: str,
    current_user: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run in-memory eligibility simulation for an application.

    Guarantees:
    - Zero modifications to persistent database rows.
    - Zero ML predictions created.
    - Zero audit logs created.
    - Uses existing active database rules and document verification summaries.
    """
    # 1. Fetch real application data from database
    try:
        app_res = (
            supabase
            .table("applications")
            .select("""
                id,
                application_number,
                applicant_id,
                scholarship_scheme_id,
                scholarship_schemes (
                    id,
                    scheme_code,
                    scheme_name,
                    required_documents
                ),
                academic_score,
                previous_score,
                attendance,
                annual_income,
                application_category,
                status
            """)
            .eq("id", application_id)
            .single()
            .execute()
        )
        app_row = app_res.data
    except Exception as exc:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.") from exc

    if not app_row:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

    # 2. Enforce Role-Based Authorization
    user_role = (current_user.get("role") or "").lower().strip()
    user_id = current_user.get("id")

    if user_role == "applicant":
        if app_row.get("applicant_id") != user_id:
            raise ForbiddenSimulationAccessError(
                "Access forbidden: You are only authorized to simulate your own application."
            )
    elif user_role == "admin":
        pass  # Admins can simulate any application
    else:
        raise ForbiddenSimulationAccessError("Access forbidden: Unauthorized role.")

    # 3. Retrieve Scheme and Active Rules from Database
    scheme_id = app_row.get("scholarship_scheme_id")
    if not scheme_id:
        raise ValueError("Application is not associated with any scholarship scheme.")

    rules = get_scholarship_rules(scheme_id)
    if not rules:
        raise ValueError("No active eligibility rules found for this scholarship scheme.")

    # 4. Fetch Real Document Verification Summary
    # CRITICAL: Document verification is NEVER mocked or altered by simulation.
    verification_summary = generate_verification_summary(application_id)

    # 5. Extract current baseline application values
    base_app_data = {
        "id": app_row["id"],
        "application_number": app_row.get("application_number"),
        "applicant_id": app_row.get("applicant_id"),
        "academic_score": float(app_row.get("academic_score", 0.0)),
        "previous_score": float(app_row.get("previous_score", 0.0)),
        "attendance": float(app_row.get("attendance", 0.0)),
        "annual_income": float(app_row.get("annual_income", 0.0)),
        "application_category": app_row.get("application_category", "GENERAL"),
    }

    # 6. Evaluate CURRENT eligibility baseline
    current_eval = evaluate_rules_for_data(
        rules=rules,
        application_data=base_app_data,
        verification_summary=verification_summary,
        application_id=application_id,
        scholarship_scheme_id=scheme_id,
    )

    # 7. Validate and apply overrides in-memory ONLY
    cleaned_overrides = validate_simulation_overrides(overrides or {})
    simulated_app_data = deepcopy(base_app_data)
    changes: Dict[str, Dict[str, Any]] = {}

    for field, new_val in cleaned_overrides.items():
        old_val = base_app_data.get(field)
        simulated_app_data[field] = new_val
        changes[field] = {
            "current": old_val,
            "simulated": new_val,
        }

    # 8. Evaluate SIMULATED eligibility on in-memory data
    simulated_eval = evaluate_rules_for_data(
        rules=rules,
        application_data=simulated_app_data,
        verification_summary=verification_summary,
        application_id=application_id,
        scholarship_scheme_id=scheme_id,
    )

    # 9. Compute rule improvements (resolved rules) and remaining failures
    current_failed_map = {r["rule_code"]: r for r in current_eval["failed_rules"]}
    simulated_failed_map = {r["rule_code"]: r for r in simulated_eval["failed_rules"]}

    improvements: List[Dict[str, Any]] = []
    for rcode, rf in current_failed_map.items():
        if rcode not in simulated_failed_map:
            # Rule was resolved by simulation
            rconfig = rf.get("rule_config") or {}
            field = rconfig.get("field", "unknown")
            improvements.append({
                "rule": rcode,
                "rule_name": rf.get("rule_name"),
                "rule_type": rf.get("rule_type"),
                "field": field,
                "current_value": base_app_data.get(field),
                "simulated_value": simulated_app_data.get(field),
                "required_value": rconfig.get("minimum") or rconfig.get("maximum") or "VERIFIED",
                "status": "RESOLVED",
            })

    remaining_failures = [
        {
            "rule": r["rule_code"],
            "rule_name": r["rule_name"],
            "rule_type": r["rule_type"],
            "status": "FAIL",
            "message": r["message"],
        }
        for r in simulated_eval["failed_rules"]
    ]

    # 10. Run Minimum-Change and Requirements Analysis
    requirements_analysis, recommended_changes = analyze_rule_requirements(
        rules=rules,
        application_data=base_app_data,
        verification_summary=verification_summary,
    )

    # 11. Determine simulation outcome flags
    is_changed = len(changes) > 0
    was_eligible = current_eval["eligible"]
    is_eligible = simulated_eval["eligible"]
    became_eligible = (not was_eligible) and is_eligible

    # 12. Build Human-Readable Explanation Message
    scheme_info = app_row.get("scholarship_schemes") or {}
    scheme_name = scheme_info.get("scheme_name") or "the selected scholarship"

    has_doc_failure = any(r["rule_type"] == "DOCUMENT_VERIFICATION" for r in simulated_eval["failed_rules"])

    if not is_changed:
        if was_eligible:
            message = f"The application currently satisfies all eligibility requirements for {scheme_name}. No changes are required."
        else:
            doc_note = " Note: document verification requirements are currently unmet." if has_doc_failure else ""
            message = (
                f"The application is currently ineligible under {len(current_eval['failed_rules'])} requirement(s) for {scheme_name}. "
                f"Review the recommended changes below to see what simulated adjustments would be needed.{doc_note}"
            )
    else:
        if is_eligible:
            message = f"With the simulated values, the application satisfies all current eligibility rules for {scheme_name}."
        else:
            if improvements:
                improved_names = ", ".join(i["rule_name"] for i in improvements)
                rem_names = ", ".join(r["rule_name"] for r in remaining_failures)
                doc_note = " Document verification requirements are still unmet." if has_doc_failure else ""
                message = (
                    f"The simulated changes resolved: {improved_names}. "
                    f"However, the application remains ineligible due to: {rem_names}.{doc_note}"
                )
            else:
                rem_names = ", ".join(r["rule_name"] for r in remaining_failures)
                doc_note = " Document verification requirements are still unmet." if has_doc_failure else ""
                message = (
                    f"With the simulated values, the application remains ineligible under: {rem_names}.{doc_note}"
                )

    # 13. Assemble and return structured frontend-ready response
    return {
        "application_id": application_id,
        "scholarship_scheme": {
            "id": scheme_id,
            "scheme_name": scheme_name,
            "scheme_code": scheme_info.get("scheme_code"),
        },
        "simulation": {
            "eligible": is_eligible,
            "changed": is_changed,
            "became_eligible": became_eligible,
        },
        "changes": changes,
        "current_result": {
            "eligible": was_eligible,
            "passed_rules": [r["rule_code"] for r in current_eval["passed_rules"]],
            "failed_rules": [r["rule_code"] for r in current_eval["failed_rules"]],
            "passed_count": current_eval["passed_count"],
            "failed_count": current_eval["failed_count"],
            "total_rules": current_eval["total_rules"],
        },
        "simulated_result": {
            "eligible": is_eligible,
            "passed_rules": [r["rule_code"] for r in simulated_eval["passed_rules"]],
            "failed_rules": [r["rule_code"] for r in simulated_eval["failed_rules"]],
            "passed_count": simulated_eval["passed_count"],
            "failed_count": simulated_eval["failed_count"],
            "total_rules": simulated_eval["total_rules"],
        },
        "improvements": improvements,
        "remaining_failures": remaining_failures,
        "requirements_analysis": requirements_analysis,
        "recommended_changes": recommended_changes,
        "message": message,
    }
