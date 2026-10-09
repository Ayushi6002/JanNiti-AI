"""
scholarship_predictor_service.py
---------------------------------
Orchestration service for the Scholarship Predictor / Eligibility Predictor feature.

Evaluates an applicant's self-reported academic, financial, category, and document profile
against active Supabase scholarship schemes and eligibility rules, producing:
1. Grounded rule-based eligibility evaluation (ELIGIBLE, NEEDS_VERIFICATION, NOT_ELIGIBLE).
2. Document readiness analysis per scheme.
3. Machine Learning model predictions and confidence scoring using the existing Random Forest model.
4. Explainable criteria breakdown (why the user qualifies or fails).
5. Dynamic ranking of active scholarships to identify the Best Match.

Strict Guarantees:
- READ-ONLY: Never creates or updates applications, human decisions, scholarship rules,
  anomaly assessments, or persistent ai_prediction records.
- Authoritative: Directly reuses Supabase scholarship_schemes, scholarship_rules, and eligibility_service.
- Transparent: Clearly separates ML confidence from rule-based eligibility probability.
"""

from typing import Any, Dict, List, Optional

try:
    from backend.supabase_client import supabase
    from backend.eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )
    from backend.ml_service import ml_service
    from backend.ml_application_service import (
        SCHOLARSHIP_SCHEME_ML_MAP,
        CATEGORY_ML_MAP,
    )
    from backend.explainable_ai_service import generate_shap_explanation
except ImportError:
    from supabase_client import supabase
    from eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )
    from ml_service import ml_service
    from ml_application_service import (
        SCHOLARSHIP_SCHEME_ML_MAP,
        CATEGORY_ML_MAP,
    )
    from explainable_ai_service import generate_shap_explanation


DOC_TYPE_LABELS = {
    "marksheet": "Academic Marksheet / Transcript",
    "id_proof": "Government Identity Proof (Aadhaar / Voter ID / PAN)",
    "income_certificate": "Income Certificate",
    "category_certificate": "Category / Caste Certificate",
}

DISCLAIMER_TEXT = (
    "This result is an AI-assisted eligibility prediction and scholarship recommendation "
    "based on the self-reported academic, financial, and document readiness information provided. "
    "It is NOT a final scholarship approval or rejection and does NOT create an official application. "
    "Official award decisions are subject to formal application submission, original document verification, "
    "and authorized human evaluator review."
)


def validate_prediction_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize the user inputs for scholarship prediction.
    Supports stage-aware academic mapping:
    - FIRST_YEAR: qualifying_score (12th/Diploma) -> academic_score, ssc_score -> previous_score, attendance = None
    - SECOND_YEAR: first_year_score -> academic_score, qualifying_score -> previous_score, attendance
    - THIRD_YEAR: second_year_score -> academic_score, first_year_score -> previous_score, attendance
    - FOURTH_YEAR: third_year_score -> academic_score, second_year_score -> previous_score, attendance
    - POSTGRADUATE: ug_score -> academic_score, previous_score, attendance
    - Legacy direct payload: academic_score, previous_score, attendance
    """
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")

    # 0. Academic Stage (Optional, default inferred or None for legacy)
    academic_stage_raw = payload.get("academic_stage")
    academic_stage = str(academic_stage_raw).strip().upper() if academic_stage_raw else None
    valid_stages = {"FIRST_YEAR", "SECOND_YEAR", "THIRD_YEAR", "FOURTH_YEAR", "POSTGRADUATE"}
    if academic_stage and academic_stage not in valid_stages:
        academic_stage = "SECOND_YEAR"

    qualification_type = payload.get("qualification_type")
    if qualification_type:
        qualification_type = str(qualification_type).strip().upper()

    # 1. Academic Score Extraction (Stage-Aware Mapping)
    raw_academic = (
        payload.get("qualifying_score")
        if academic_stage == "FIRST_YEAR" and payload.get("qualifying_score") is not None
        else payload.get("first_year_score")
        if academic_stage == "SECOND_YEAR" and payload.get("first_year_score") is not None
        else payload.get("second_year_score")
        if academic_stage == "THIRD_YEAR" and payload.get("second_year_score") is not None
        else payload.get("third_year_score")
        if academic_stage == "FOURTH_YEAR" and payload.get("third_year_score") is not None
        else payload.get("ug_score")
        if academic_stage == "POSTGRADUATE" and payload.get("ug_score") is not None
        else payload.get("academic_score")
    )

    if raw_academic is None or raw_academic == "":
        label = (
            "Qualifying examination score" if academic_stage == "FIRST_YEAR"
            else "First year college percentage" if academic_stage == "SECOND_YEAR"
            else "Second year college percentage" if academic_stage == "THIRD_YEAR"
            else "Third year college percentage" if academic_stage == "FOURTH_YEAR"
            else "Academic score"
        )
        raise ValueError(f"{label} is required.")
    try:
        academic_score = float(raw_academic)
    except (ValueError, TypeError) as exc:
        raise ValueError("Academic score must be a valid numeric percentage.") from exc
    if not (0.0 <= academic_score <= 100.0):
        raise ValueError("Academic score must be between 0 and 100.")

    # 2. Previous Academic Score Extraction (Stage-Aware Mapping)
    raw_previous = (
        payload.get("ssc_score")
        if academic_stage == "FIRST_YEAR" and payload.get("ssc_score") is not None
        else payload.get("qualifying_score")
        if academic_stage == "SECOND_YEAR" and payload.get("qualifying_score") is not None
        else payload.get("first_year_score")
        if academic_stage == "THIRD_YEAR" and payload.get("first_year_score") is not None
        else payload.get("second_year_score")
        if academic_stage == "FOURTH_YEAR" and payload.get("second_year_score") is not None
        else payload.get("previous_score")
    )

    if raw_previous is None or raw_previous == "":
        if academic_stage in ("FIRST_YEAR", "SECOND_YEAR", "THIRD_YEAR", "FOURTH_YEAR", "POSTGRADUATE"):
            # If prior score not specified, default to latest academic_score
            previous_score = academic_score
        else:
            raise ValueError("Previous academic score is required.")
    else:
        try:
            previous_score = float(raw_previous)
        except (ValueError, TypeError) as exc:
            raise ValueError("Previous academic score must be a valid numeric percentage.") from exc
        if not (0.0 <= previous_score <= 100.0):
            raise ValueError("Previous academic score must be between 0 and 100.")

    # 3. Attendance Extraction (Stage-Aware: None for FIRST_YEAR)
    attendance = None
    if academic_stage == "FIRST_YEAR":
        # College attendance is strictly not applicable for first-year fresh admission
        attendance = None
    else:
        raw_att = payload.get("attendance")
        if raw_att is None or raw_att == "":
            raise ValueError("Attendance is required.")
        try:
            attendance = float(raw_att)
        except (ValueError, TypeError) as exc:
            raise ValueError("Attendance must be a valid numeric percentage.") from exc
        if not (0.0 <= attendance <= 100.0):
            raise ValueError("Attendance must be between 0 and 100.")

    # 4. Annual Income
    if "annual_income" not in payload or payload["annual_income"] is None or payload["annual_income"] == "":
        raise ValueError("Annual family income is required.")
    try:
        annual_income = float(payload["annual_income"])
    except (ValueError, TypeError) as exc:
        raise ValueError("Annual income must be a valid numeric amount.") from exc
    if annual_income < 0.0:
        raise ValueError("Annual family income cannot be negative.")

    # 5. Application Category (Optional, default GENERAL)
    category_raw = payload.get("application_category") or "GENERAL"
    category = str(category_raw).strip().upper() or "GENERAL"

    # 6. Document Checklist (dictionary of doc_type -> boolean)
    docs_raw = payload.get("documents") or {}
    if not isinstance(docs_raw, dict):
        raise ValueError("Documents checklist must be an object with document keys and boolean values.")
    documents = {str(k).strip().lower(): bool(v) for k, v in docs_raw.items()}

    return {
        "academic_stage": academic_stage,
        "qualification_type": qualification_type,
        "academic_score": academic_score,
        "previous_score": previous_score,
        "attendance": attendance,
        "annual_income": annual_income,
        "application_category": category,
        "documents": documents,
    }


def _format_rule_title(rule: Dict[str, Any]) -> str:
    """Format rule code and config into a clean human-readable criteria title."""
    rtype = rule.get("rule_type")
    rconfig = rule.get("rule_config") or {}
    field = rconfig.get("field", "")

    if rtype == "MIN_VALUE":
        min_val = rconfig.get("minimum", 0)
        if field == "academic_score":
            return f"Academic Score ≥ {min_val}%"
        if field == "previous_score":
            return f"Previous Score ≥ {min_val}%"
        if field == "attendance":
            return f"Attendance Record ≥ {min_val}%"
        return f"{field.replace('_', ' ').title()} ≥ {min_val}"

    if rtype == "MAX_VALUE":
        max_val = rconfig.get("maximum", 0)
        if field == "annual_income":
            return f"Annual Family Income ≤ ₹{int(max_val):,}"
        return f"{field.replace('_', ' ').title()} ≤ {max_val}"

    if rtype == "DOCUMENT_VERIFICATION":
        return "Required Documents Checklist"

    return rule.get("rule_name") or rule.get("rule_code") or "Eligibility requirement"


def get_authoritative_active_schemes() -> List[Dict[str, Any]]:
    """
    Fetch all active scholarship schemes directly from the authoritative Supabase configuration.
    Guarantees no stale or artificial hardcoded schemes.
    """
    response = (
        supabase
        .table("scholarship_schemes")
        .select("id, scheme_code, scheme_name, description, required_documents, is_active")
        .eq("is_active", True)
        .order("scheme_name")
        .execute()
    )
    return response.data or []


def predict_scholarships(profile_data: Dict[str, Any], applicant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute read-only scholarship prediction across all active scholarship schemes.

    Args:
        profile_data: Validated dictionary containing academic_score, previous_score,
                      attendance, annual_income, application_category, and documents.

    Returns:
        Structured response with Best Match, other matches, criteria evaluations,
        ML model inference, document readiness, and safety disclaimers.
    """
    cleaned = validate_prediction_input(profile_data)
    academic_stage = cleaned.get("academic_stage")
    qualification_type = cleaned.get("qualification_type")
    academic_score = cleaned["academic_score"]
    previous_score = cleaned["previous_score"]
    attendance = cleaned["attendance"]
    annual_income = cleaned["annual_income"]
    category = cleaned["application_category"]
    student_docs = cleaned["documents"]

    # 1. Fetch active schemes from authoritative Supabase source
    active_schemes = get_authoritative_active_schemes()
    if not active_schemes:
        return {
            "success": False,
            "error": "No active scholarship schemes are currently configured.",
            "schemes": [],
            "best_match": None,
            "disclaimer": DISCLAIMER_TEXT,
        }

    evaluated_schemes: List[Dict[str, Any]] = []

    for scheme in active_schemes:
        scheme_id = scheme["id"]
        scheme_code = scheme.get("scheme_code") or "SCHOLARSHIP"
        scheme_name = scheme.get("scheme_name") or "Scholarship"
        description = scheme.get("description") or ""
        required_docs: List[str] = scheme.get("required_documents") or []

        # 2. Build in-memory document verification summary for this scheme
        missing_docs: List[str] = []
        ready_docs: List[str] = []
        verification_items: List[Dict[str, Any]] = []

        for dt in required_docs:
            is_ready = bool(student_docs.get(dt, False))
            label = DOC_TYPE_LABELS.get(dt, dt.replace("_", " ").title())
            status = "VERIFIED" if is_ready else "MISSING"

            if is_ready:
                ready_docs.append(dt)
            else:
                missing_docs.append(dt)

            verification_items.append({
                "document_type": dt,
                "document_label": label,
                "status": status,
                "is_ready": is_ready,
            })

        overall_doc_status = "VERIFIED" if (len(missing_docs) == 0 and len(required_docs) > 0) else "INCOMPLETE"

        v_summary = {
            "scheme_name": scheme_name,
            "required_documents": list(required_docs),
            "documents": {
                item["document_type"]: {"status": item["status"]}
                for item in verification_items
            },
            "missing_documents": missing_docs,
            "overall_status": overall_doc_status,
        }

        # 3. Retrieve authoritative rules from Supabase for this scheme
        rules = get_scholarship_rules(scheme_id)

        # 4. Evaluate profile against rules using the existing pure evaluator
        app_data = {
            "academic_score": academic_score,
            "previous_score": previous_score,
            "attendance": attendance,
            "annual_income": annual_income,
            "application_category": category,
        }

        # Stage-Aware Rule Evaluation:
        # First-year applicants do not have college attendance history.
        # Evaluate academic and financial requirements without demanding non-existent college attendance.
        if academic_stage == "FIRST_YEAR":
            eval_rules = [r for r in rules if r.get("rule_config", {}).get("field") != "attendance"]
        else:
            eval_rules = rules

        eval_result = evaluate_rules_for_data(
            rules=eval_rules,
            application_data=app_data,
            verification_summary=v_summary,
            scholarship_scheme_id=scheme_id,
        )

        passed_rules = eval_result.get("passed_rules", [])
        failed_rules = eval_result.get("failed_rules", [])
        total_rules = eval_result.get("total_rules", 0)

        numeric_failed = [r for r in failed_rules if r.get("rule_type") != "DOCUMENT_VERIFICATION"]
        doc_failed = [r for r in failed_rules if r.get("rule_type") == "DOCUMENT_VERIFICATION"]

        # Exact criteria match percentage based on configured rules
        match_percentage = round((len(passed_rules) / total_rules) * 100) if total_rules > 0 else 0

        # Eligibility Status Determination:
        # - NOT_ELIGIBLE: Any numeric or substantive eligibility rule fails
        # - NEEDS_VERIFICATION: All numeric rules pass, but one or more required documents are missing
        # - ELIGIBLE: All numeric rules pass and all required documents are marked ready
        if len(numeric_failed) > 0:
            eligibility_status = "NOT_ELIGIBLE"
        elif len(doc_failed) > 0 or overall_doc_status != "VERIFIED":
            eligibility_status = "NEEDS_VERIFICATION"
        else:
            eligibility_status = "ELIGIBLE"

        # 5. ML Model Prediction via Versioned MLService
        cat_raw = category
        if ml_service.active_version == "stage_aware_v1":
            from backend.ml_application_service import CANONICAL_CATEGORY_ML_MAP
            cat_mapped = CANONICAL_CATEGORY_ML_MAP.get(cat_raw, "General")
            if cat_mapped not in ml_service.encoders["application_category"].classes_:
                cat_mapped = "General"
        else:
            cat_mapped = CATEGORY_ML_MAP.get(cat_raw)
            if not cat_mapped:
                cat_title = cat_raw.replace("_", " ").title()
                if cat_title in ml_service.encoders["application_category"].classes_:
                    cat_mapped = cat_title
                else:
                    cat_mapped = "General"

        scheme_mapped = (
            SCHOLARSHIP_SCHEME_ML_MAP.get(scheme_name)
            or SCHOLARSHIP_SCHEME_ML_MAP.get(scheme_code)
            or "Merit Scholarship"
        )

        if ml_service.active_version == "stage_aware_v1":
            # Stage-aware model directly handles First-Year and continuing students
            ml_input = {
                "academic_stage": academic_stage or ("FIRST_YEAR" if attendance is None else "SECOND_YEAR"),
                "qualification_type": qualification_type or "HSC_12TH",
                "academic_score": academic_score,
                "previous_score": previous_score,
                "attendance": attendance,
                "is_attendance_applicable": 0 if (academic_stage == "FIRST_YEAR" or attendance is None) else 1,
                "annual_income": annual_income,
                "application_category": cat_mapped,
                "scholarship_scheme": scheme_mapped,
                "documents_verified": overall_doc_status,
                "documents_verified_contract": "VERIFIED_SERVICE" if overall_doc_status == "VERIFIED" else "KNOWN_INCOMPLETE",
            }

            ml_result = ml_service.predict_and_explain(ml_input)
            prob_approve = float(ml_result.get("estimated_approval_probability", 0.0))
            raw_confidence = prob_approve

            has_disagreement = (eligibility_status == "NOT_ELIGIBLE" and ml_result.get("final_decision") == "APPROVE")
            ml_advisory_note = None
            if has_disagreement:
                ml_advisory_note = (
                    "The AI model's prediction is an advisory signal based on historical training data. "
                    "Current scholarship eligibility rules take precedence. "
                    "This means the applicant's historical feature pattern resembles cases the model associated with approval; "
                    "it does NOT override current scholarship eligibility rules."
                )

            is_approval_applicable = (eligibility_status == "ELIGIBLE" and ml_result.get("final_decision") == "APPROVE")
            if is_approval_applicable:
                approval_prob_display = f"{prob_approve * 100:.2f}%"
                approval_prob_note = (
                    "Estimated probability of the APPROVE outcome from the AI model. "
                    "This is an advisory estimate and does not guarantee approval."
                )
            elif eligibility_status == "NOT_ELIGIBLE":
                approval_prob_display = "Not applicable"
                approval_prob_note = "Current eligibility rules are not satisfied."
            else:
                approval_prob_display = "Not applicable"
                approval_prob_note = "Verification or non-approval outcome; approval probability is not applicable."

            shap_result = generate_shap_explanation(ml_input)

        elif academic_stage == "FIRST_YEAR" or attendance is None:
            # Legacy first-year admission fallback: college attendance is not available.
            # The 7-feature model requires college attendance to produce a validated estimate.
            raw_confidence = 0.0
            is_approval_applicable = False
            approval_prob_display = "Not applicable"
            approval_prob_note = "College attendance is not applicable for first-year admission; current ML model requires college attendance."
            has_disagreement = False
            ml_advisory_note = (
                "First-year applicants do not have college attendance records. "
                "Because the current AI model requires college attendance to produce a validated assessment, "
                "an automated probability cannot be calculated. Human review is recommended."
            )
            ml_result = {
                "model_decision": "NEEDS_HUMAN_REVIEW",
                "final_decision": "NEEDS_HUMAN_REVIEW",
                "confidence": 0.0,
                "top_reasons": [],
                "override_applied": "First-year admission: college attendance is not available; routed to human review.",
            }
            shap_result = {
                "status": "unavailable",
                "message": "Model explainability is not applicable for first-year admission profiles because college attendance is not available.",
            }
        else:
            ml_input = {
                "academic_score": academic_score,
                "previous_score": previous_score,
                "attendance": attendance,
                "annual_income": annual_income,
                "application_category": cat_mapped,
                "scholarship_scheme": scheme_mapped,
                "documents_verified": overall_doc_status,
                "documents_verified_contract": "VERIFIED_SERVICE" if overall_doc_status == "VERIFIED" else "KNOWN_INCOMPLETE",
            }

            ml_result = ml_service.predict_and_explain(ml_input)
            raw_confidence = float(ml_result.get("confidence", 0.0))
            has_disagreement = (eligibility_status == "NOT_ELIGIBLE" and ml_result.get("final_decision") == "APPROVE")
            ml_advisory_note = None
            if has_disagreement:
                ml_advisory_note = (
                    "The AI model's prediction is an advisory signal based on historical training data. "
                    "Current scholarship eligibility rules take precedence. "
                    "This means the applicant's historical feature pattern resembles cases the model associated with approval; "
                    "it does NOT override current scholarship eligibility rules."
                )

            # Defensible Approval Probability:
            # Applicable ONLY when deterministic eligibility is satisfied (ELIGIBLE) and AI predicts APPROVE.
            is_approval_applicable = (eligibility_status == "ELIGIBLE" and ml_result.get("final_decision") == "APPROVE")
            if is_approval_applicable:
                approval_prob_display = f"{raw_confidence * 100:.2f}%"
                approval_prob_note = (
                    "Estimated probability of the APPROVE outcome from the AI model. "
                    "This is an advisory estimate and does not guarantee approval."
                )
            elif eligibility_status == "NOT_ELIGIBLE":
                approval_prob_display = "Not applicable"
                approval_prob_note = "Current eligibility rules are not satisfied."
            else:
                approval_prob_display = "Not applicable"
                approval_prob_note = "Verification or non-approval outcome; approval probability is not applicable."

            shap_result = generate_shap_explanation(ml_input)

        # 6. Format Detailed Criteria Breakdowns
        passed_criteria: List[Dict[str, Any]] = []
        for r in passed_rules:
            passed_criteria.append({
                "rule_code": r.get("rule_code"),
                "rule_name": r.get("rule_name"),
                "rule_type": r.get("rule_type"),
                "title": _format_rule_title(r),
                "message": r.get("message", "Requirement satisfied."),
                "status": "PASS",
            })

        if academic_stage == "FIRST_YEAR":
            passed_criteria.append({
                "rule_code": "ATTENDANCE_NOT_APPLICABLE",
                "rule_name": "College Attendance",
                "rule_type": "MIN_VALUE",
                "title": "College Attendance Record",
                "message": "College attendance requirement is not applicable for first-year fresh admission (waived).",
                "status": "PASS",
            })

        failed_criteria: List[Dict[str, Any]] = []
        for r in numeric_failed:
            failed_criteria.append({
                "rule_code": r.get("rule_code"),
                "rule_name": r.get("rule_name"),
                "rule_type": r.get("rule_type"),
                "title": _format_rule_title(r),
                "message": r.get("message", "Criteria threshold not met."),
                "actual_value": r.get("details", {}).get("actual_value"),
                "required_value": r.get("details", {}).get("required_value"),
                "status": "FAIL",
            })

        # 7. Formulate Traceable Explanations
        missing_labels = [DOC_TYPE_LABELS.get(d, d.replace("_", " ").title()) for d in missing_docs]
        if eligibility_status == "ELIGIBLE":
            explanation = (
                f"You currently satisfy all configured academic, financial, and document readiness "
                f"criteria for the {scheme_name}."
            )
            next_action = "You meet all configured requirements. Proceed to formal application."
        elif eligibility_status == "NEEDS_VERIFICATION":
            missing_str = ", ".join(missing_labels) if missing_labels else "required documents"
            explanation = (
                f"You meet the academic and financial requirements for {scheme_name}, but "
                f"verification readiness is incomplete. Missing: {missing_str}."
            )
            next_action = f"Gather and ensure you have: {missing_str} before applying."
        else: # NOT_ELIGIBLE
            failed_reasons = [r.get("message", "Threshold not met") for r in numeric_failed]
            explanation = f"Criteria not satisfied: {'; '.join(failed_reasons)}."
            next_action = "Review alternative scholarship schemes where your profile matches configured criteria."

        evaluated_schemes.append({
            "scheme_id": scheme_id,
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "description": description,
            "eligibility_status": eligibility_status,
            "match_percentage": match_percentage,
            "is_eligible": eligibility_status == "ELIGIBLE",
            "needs_verification": eligibility_status == "NEEDS_VERIFICATION",
            "ml_prediction": {
                "decision": ml_result.get("final_decision"),
                "prediction": ml_result.get("final_decision"),
                "model_decision": ml_result.get("model_decision"),
                "model_version": ml_result.get("model_version", ml_service.active_version),
                "confidence": round(raw_confidence, 4),
                "confidence_score": round(raw_confidence, 4),
                "confidence_display": f"{raw_confidence * 100:.2f}%",
                "is_approval_applicable": is_approval_applicable,
                "estimated_approval_probability": approval_prob_display,
                "approval_probability_note": approval_prob_note,
                "has_disagreement": has_disagreement,
                "top_reasons": ml_result.get("top_reasons", []),
                "override_applied": ml_result.get("override_applied"),
                "advisory_note": ml_advisory_note,
                "shap_explanation": shap_result,
            },
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "document_readiness": {
                "overall_status": overall_doc_status,
                "readiness_status": "READY" if (len(missing_docs) == 0 and len(required_docs) > 0) else "INCOMPLETE",
                "verification_status": "UNCERTAIN",
                "verification_authority_note": (
                    "Predictor checkboxes represent applicant-declared document availability (readiness). "
                    "Official document verification is conducted solely by the verification service upon formal application submission."
                ),
                "required_documents_count": len(required_docs),
                "ready_count": len(ready_docs),
                "missing_count": len(missing_docs),
                "items": verification_items,
                "missing_labels": missing_labels,
            },
            "rules_count": {
                "total": total_rules,
                "passed": len(passed_rules),
                "failed": len(failed_rules),
            },
            "passed_rules_count": len(passed_rules),
            "failed_rules_count": len(failed_rules),
            "missing_documents": missing_docs,
            "explanation": explanation,
            "next_action": next_action,
        })

    # 8. Transparent Ranking Methodology:
    # Priority order:
    #   Rank 0: ELIGIBLE (sorted by match_percentage DESC, then ml_confidence DESC)
    #   Rank 1: NEEDS_VERIFICATION (sorted by match_percentage DESC, then ml_confidence DESC)
    #   Rank 2: NOT_ELIGIBLE (sorted by match_percentage DESC, then ml_confidence DESC)
    status_order = {"ELIGIBLE": 0, "NEEDS_VERIFICATION": 1, "NOT_ELIGIBLE": 2}
    evaluated_schemes.sort(
        key=lambda s: (
            status_order.get(s["eligibility_status"], 99),
            -s["match_percentage"],
            -s["ml_prediction"]["confidence_score"],
        )
    )

    eligible_schemes = [s for s in evaluated_schemes if s["eligibility_status"] == "ELIGIBLE"]
    needs_verif_schemes = [s for s in evaluated_schemes if s["eligibility_status"] == "NEEDS_VERIFICATION"]
    not_eligible_schemes = [s for s in evaluated_schemes if s["eligibility_status"] == "NOT_ELIGIBLE"]

    # Determine Best Match
    best_match: Optional[Dict[str, Any]] = None
    if eligible_schemes:
        best_match = eligible_schemes[0]
    elif needs_verif_schemes:
        best_match = needs_verif_schemes[0]
    # Global document readiness across all active schemes
    global_all_docs = set()
    for s in active_schemes:
        for d in (s.get("required_documents") or []):
            global_all_docs.add(d)
    global_provided_docs = [d for d in global_all_docs if student_docs.get(d)]
    global_missing_docs = [d for d in global_all_docs if not student_docs.get(d)]

    return {
        "success": True,
        "profile_evaluated": {
            "academic_score": academic_score,
            "previous_score": previous_score,
            "attendance": attendance,
            "annual_income": annual_income,
            "application_category": category,
            "documents_checked_count": sum(1 for v in student_docs.values() if v),
        },
        "summary": {
            "total_schemes_evaluated": len(evaluated_schemes),
            "eligible_count": len(eligible_schemes),
            "needs_verification_count": len(needs_verif_schemes),
            "not_eligible_count": len(not_eligible_schemes),
            "has_eligible_match": len(eligible_schemes) > 0,
        },
        "best_match": best_match,
        "schemes": evaluated_schemes,
        "all_scholarships": evaluated_schemes,
        "eligible_count": len(eligible_schemes),
        "total_evaluated": len(evaluated_schemes),
        "document_readiness": {
            "complete": len(global_missing_docs) == 0,
            "readiness_status": "READY" if len(global_missing_docs) == 0 else "INCOMPLETE",
            "verification_status": "UNCERTAIN",
            "verification_authority_note": (
                "Predictor checkboxes represent applicant-declared document availability (readiness). "
                "Official document verification is conducted solely by the verification service upon formal application submission."
            ),
            "provided": sorted(global_provided_docs),
            "missing": sorted(global_missing_docs),
            "total_tracked": len(global_all_docs),
        },
        "shap_explanation": (
            best_match["ml_prediction"].get("shap_explanation")
            if (best_match and best_match.get("ml_prediction"))
            else (evaluated_schemes[0]["ml_prediction"].get("shap_explanation") if evaluated_schemes else None)
        ),
        "disclaimer": DISCLAIMER_TEXT,
    }


def get_predictor_configuration() -> Dict[str, Any]:
    """
    Return active schemes, required document checklist items, and validation constraints
    for initializing the frontend predictor form without any hardcoded JavaScript rules.
    """
    schemes = get_authoritative_active_schemes()
    all_required_docs = set()
    for s in schemes:
        for doc in (s.get("required_documents") or []):
            all_required_docs.add(doc)

    checklist_items = [
        {
            "id": doc,
            "type": doc,
            "label": DOC_TYPE_LABELS.get(doc, doc.replace("_", " ").title()),
            "description": f"Required for {', '.join([s.get('scheme_name') for s in schemes if doc in (s.get('required_documents') or [])])}",
        }
        for doc in sorted(all_required_docs)
    ]

    return {
        "success": True,
        "active_schemes": [
            {
                "id": s["id"],
                "scheme_code": s.get("scheme_code"),
                "scheme_name": s.get("scheme_name"),
                "description": s.get("description"),
                "required_documents": s.get("required_documents") or [],
            }
            for s in schemes
        ],
        "document_checklist": checklist_items,
        "all_required_documents": checklist_items,
        "constraints": {
            "academic_score": {"min": 0, "max": 100, "step": 0.1},
            "previous_score": {"min": 0, "max": 100, "step": 0.1},
            "attendance": {"min": 0, "max": 100, "step": 0.1},
            "annual_income": {"min": 0, "step": 1000},
        },
        "disclaimer": DISCLAIMER_TEXT,
    }
