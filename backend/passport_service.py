"""
passport_service.py
-------------------
Service for generating the AI Decision Passport for scholarship applications.
Exposes explainability, document verification, rule eligibility, AI recommendations,
human decisions, audit logs, and appeal status in a clean, structured payload.
"""

from typing import Any, Dict, List, Optional

try:
    from backend.application_service import get_application_full_details
    from backend.verification_service import generate_verification_summary
    from backend.eligibility_service import evaluate_application_eligibility
except ImportError:
    from application_service import get_application_full_details
    from verification_service import generate_verification_summary
    from eligibility_service import evaluate_application_eligibility


class ApplicationNotFoundError(Exception):
    """Raised when an application is not found."""
    pass


class ForbiddenPassportAccessError(Exception):
    """Raised when a user is not authorized to access an application's passport."""
    pass


FEATURE_LABELS = {
    "academic_score": "academic score",
    "previous_score": "previous academic score",
    "attendance": "attendance record",
    "annual_income": "family income level",
    "application_category": "application category",
    "scholarship_scheme": "scholarship scheme",
    "documents_verified": "document verification status",
}


def build_readable_reason(reason_item: Dict[str, Any]) -> str:
    """
    Format a SHAP explanation reason into a clear, neutral statement
    avoiding unwarranted causal claims.
    """
    feat = reason_item.get("feature", "")
    direction = reason_item.get("direction", "")
    impact = abs(float(reason_item.get("impact", 0)))
    label = FEATURE_LABELS.get(feat, feat.replace("_", " "))

    if direction == "increased":
        return (
            f"{label.capitalize()} positively influenced the recommendation "
            f"and was an important model factor (impact: {impact:.2f})."
        )
    return (
        f"{label.capitalize()} negatively influenced the recommendation "
        f"and was an important model factor (impact: {impact:.2f})."
    )


def build_decision_passport(application_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compile and return the complete AI Decision Passport for an application.

    Enforces authorization:
      - Admin users can view any application.
      - Applicant users can ONLY view applications where applicant_id matches their user id.
      - Other roles or unauthenticated users are denied.
    """
    # 1. Retrieve application full details from existing service
    try:
        details = get_application_full_details(application_id)
    except Exception as exc:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.") from exc

    if not details or not details.get("application"):
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

    app_data = details["application"]
    applicant_id = app_data.get("applicant_id")

    # 2. Enforce Role-Based Authorization
    user_role = (current_user.get("role") or "").lower().strip()
    user_id = current_user.get("id")

    if user_role == "applicant":
        if applicant_id != user_id:
            raise ForbiddenPassportAccessError(
                "Access forbidden: You are only authorized to view your own application's Decision Passport."
            )
    elif user_role == "admin":
        pass  # Admins are authorized to view all applications
    else:
        raise ForbiddenPassportAccessError("Access forbidden: Unauthorized role.")

    # 3. Application Information
    scheme = app_data.get("scholarship_schemes") or {}
    scheme_name = scheme.get("scheme_name") or scheme.get("scheme_code") or "Scholarship"
    scheme_code = scheme.get("scheme_code") or "UNKNOWN"
    scheme_id = app_data.get("scholarship_scheme_id")

    # 4. Human Decision (distinguished from AI recommendation)
    decisions = details.get("decisions") or []
    latest_decision = decisions[0] if decisions else None

    if latest_decision:
        human_decision_payload: Optional[Dict[str, Any]] = {
            "has_decision": True,
            "decision": latest_decision.get("decision"),
            "decision_type": latest_decision.get("decision_type", "HUMAN"),
            "decided_by": latest_decision.get("decided_by"),
            "reason": latest_decision.get("reason"),
            "admin_comment": latest_decision.get("admin_comment"),
            "decided_at": latest_decision.get("created_at"),
        }
        final_decision_val = latest_decision.get("decision")
    else:
        human_decision_payload = None
        final_decision_val = None

    application_payload = {
        "id": app_data["id"],
        "application_number": app_data.get("application_number"),
        "applicant_id": applicant_id,
        "scholarship_scheme": scheme_name,
        "scholarship_scheme_code": scheme_code,
        "status": app_data.get("status"),
        "final_decision": final_decision_val,
        "academic_score": app_data.get("academic_score"),
        "previous_score": app_data.get("previous_score"),
        "attendance": app_data.get("attendance"),
        "annual_income": app_data.get("annual_income"),
        "application_category": app_data.get("application_category"),
        "created_at": app_data.get("created_at"),
        "updated_at": app_data.get("updated_at"),
    }

    # 5. Eligibility Summary
    eligibility_summary = None
    if scheme_id:
        try:
            eligibility_summary = evaluate_application_eligibility(application_id, scheme_id)
        except Exception:
            eligibility_summary = None

    if eligibility_summary:
        failed_rules = eligibility_summary.get("failed_rules") or []
        passed_rules = eligibility_summary.get("passed_rules") or []
        failed_reasons = [
            r.get("message") for r in failed_rules if r.get("message")
        ]

        eligibility_payload = {
            "eligible": eligibility_summary.get("eligible", False),
            "eligibility_score": app_data.get("eligibility_score", None),
            "passed_count": eligibility_summary.get("passed_count", len(passed_rules)),
            "failed_count": eligibility_summary.get("failed_count", len(failed_rules)),
            "total_rules": eligibility_summary.get("total_rules", len(passed_rules) + len(failed_rules)),
            "passed_rules": [
                {
                    "rule_code": r.get("rule_code"),
                    "rule_name": r.get("rule_name"),
                    "rule_type": r.get("rule_type"),
                    "status": r.get("status"),
                    "message": r.get("message"),
                }
                for r in passed_rules
            ],
            "failed_rules": [
                {
                    "rule_code": r.get("rule_code"),
                    "rule_name": r.get("rule_name"),
                    "rule_type": r.get("rule_type"),
                    "status": r.get("status"),
                    "message": r.get("message"),
                }
                for r in failed_rules
            ],
            "failed_reasons": failed_reasons,
        }
    else:
        eligibility_payload = {
            "eligible": None,
            "eligibility_score": None,
            "passed_count": 0,
            "failed_count": 0,
            "total_rules": 0,
            "passed_rules": [],
            "failed_rules": [],
            "failed_reasons": [],
        }

    # 6. Document Verification Summary
    ver_summary = None
    try:
        ver_summary = generate_verification_summary(application_id)
    except Exception:
        ver_summary = None

    if ver_summary:
        req_docs = ver_summary.get("required_documents") or []
        docs_dict = ver_summary.get("documents") or {}
        missing_docs = ver_summary.get("missing_documents") or []
        mismatched_docs = ver_summary.get("mismatched_documents") or []
        needs_review_docs = ver_summary.get("needs_review_documents") or []

        verified_count = sum(
            1 for d in docs_dict.values() if isinstance(d, dict) and d.get("status") == "VERIFIED"
        )

        items = []
        for req_type in req_docs:
            doc_info = docs_dict.get(req_type, {})
            status = doc_info.get("status", "MISSING")
            items.append({
                "document_type": req_type,
                "verification_status": status,
                "verification_score": doc_info.get("score"),
                "file_name": doc_info.get("file_name"),
                "mismatch_details": doc_info.get("mismatch_details"),
                "verified_at": doc_info.get("verified_at"),
                "is_required": True,
            })

        # Add any uploaded document not listed in required_documents
        uploaded_docs = details.get("documents") or []
        for doc in uploaded_docs:
            dtype = doc.get("document_type")
            if dtype and dtype not in req_docs:
                items.append({
                    "document_type": dtype,
                    "verification_status": doc.get("verification_status"),
                    "verification_score": doc.get("verification_score"),
                    "file_name": doc.get("file_name"),
                    "mismatch_details": doc.get("mismatch_details"),
                    "verified_at": doc.get("verified_at"),
                    "is_required": False,
                })

        documents_payload = {
            "overall_status": ver_summary.get("overall_status", "INCOMPLETE"),
            "required_count": len(req_docs),
            "verified_count": verified_count,
            "documents_needing_review": needs_review_docs,
            "missing_documents": missing_docs,
            "mismatched_documents": mismatched_docs,
            "items": items,
        }
    else:
        documents_payload = {
            "overall_status": "UNKNOWN",
            "required_count": 0,
            "verified_count": 0,
            "documents_needing_review": [],
            "missing_documents": [],
            "mismatched_documents": [],
            "items": [],
        }

    # 7. AI Recommendation
    latest_pred = details.get("ai_prediction")
    if latest_pred:
        raw_reasons = latest_pred.get("top_reasons") or []
        readable_reasons = [build_readable_reason(r) for r in raw_reasons if isinstance(r, dict)]

        override_applied = None
        exp = latest_pred.get("explanation")
        if isinstance(exp, dict):
            override_applied = exp.get("override_applied")

        ai_payload: Optional[Dict[str, Any]] = {
            "prediction": latest_pred.get("prediction"),
            "probability": float(latest_pred.get("probability", 0)),
            "confidence": float(latest_pred.get("probability", 0)),
            "model_version": latest_pred.get("model_version", "jan_niti_rf_v2"),
            "top_reasons": raw_reasons,
            "readable_reasons": readable_reasons,
            "feature_breakdown": latest_pred.get("feature_breakdown") or raw_reasons,
            "override_applied": override_applied,
            "disclaimer": (
                "AI recommendations are advisory only and assist human reviewers. "
                "The final decision is always made by an authorized human evaluator."
            ),
            "predicted_at": latest_pred.get("created_at"),
        }
    else:
        ai_payload = None

    # 8. Audit Information
    audit_logs = details.get("audit_logs") or []
    status_changes = []
    decision_events = []

    for a in audit_logs:
        act = a.get("action")
        if act == "STATUS_CHANGED":
            old_val = a.get("old_value")
            new_val = a.get("new_value")
            status_changes.append({
                "id": a.get("id"),
                "action": act,
                "old_status": old_val.get("status") if isinstance(old_val, dict) else old_val,
                "new_status": new_val.get("status") if isinstance(new_val, dict) else new_val,
                "reason": a.get("reason"),
                "actor_id": a.get("actor_id"),
                "timestamp": a.get("created_at"),
            })

        if act in {"STATUS_CHANGED", "HUMAN_DECISION", "DECISION_RECORDED"}:
            decision_events.append({
                "id": a.get("id"),
                "action": act,
                "actor_id": a.get("actor_id"),
                "reason": a.get("reason"),
                "old_value": a.get("old_value"),
                "new_value": a.get("new_value"),
                "timestamp": a.get("created_at"),
            })

    audit_payload = {
        "status_changes": status_changes,
        "decision_events": decision_events,
        "total_events": len(audit_logs),
    }

    # 9. Appeal Information
    appeals = details.get("appeals") or []
    latest_appeal = appeals[0] if appeals else None

    if latest_appeal:
        appeal_payload = {
            "has_appeal": True,
            "id": latest_appeal.get("id"),
            "status": latest_appeal.get("status"),
            "reason": latest_appeal.get("reason"),
            "review_comment": latest_appeal.get("review_comment"),
            "submitted_at": latest_appeal.get("created_at"),
            "updated_at": latest_appeal.get("updated_at"),
        }
    else:
        appeal_payload = {
            "has_appeal": False,
            "status": None,
        }

    # 10. Assemble and Return Decision Passport
    return {
        "application": application_payload,
        "eligibility": eligibility_payload,
        "documents": documents_payload,
        "ai_recommendation": ai_payload,
        "human_decision": human_decision_payload,
        "audit": audit_payload,
        "appeal": appeal_payload,
    }
