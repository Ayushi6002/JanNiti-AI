"""
copilot_service.py
------------------
AI Scholarship Eligibility Copilot service for Jan Niti AI.
Provides an explainable, rule-grounded scholarship eligibility assistant.

Source of Truth:
- Supabase scholarship_schemes table
- Supabase scholarship_rules table
- backend/eligibility_service.py (evaluate_rules_for_data)

Guarantees:
- Strictly read-only: zero database writes, zero application status changes, zero decision modifications.
- No LLM hallucinations: all explanations are directly traced to configured database rules.
- Grounded categories: ELIGIBLE, NEEDS_VERIFICATION, NOT_ELIGIBLE.
- Accurate match percentage: passed_rules / total_rules * 100.
"""

from typing import Any, Dict, List, Optional

try:
    from backend.supabase_client import supabase
    from backend.application_service import (
        get_applicant_profile,
        get_applications_by_applicant,
    )
    from backend.verification_service import get_application_documents
    from backend.eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )
except ImportError:
    from supabase_client import supabase
    from application_service import (
        get_applicant_profile,
        get_applications_by_applicant,
    )
    from verification_service import get_application_documents
    from eligibility_service import (
        get_scholarship_rules,
        evaluate_rules_for_data,
    )


DOC_TYPE_LABELS = {
    "marksheet": "Academic Marksheet",
    "id_proof": "Government ID Proof",
    "income_certificate": "Income Certificate",
    "category_certificate": "Category / Caste Certificate",
}


def _format_rule_title(rule: Dict[str, Any]) -> str:
    """Format rule code and config into a clean human-readable criteria title."""
    rtype = rule.get("rule_type")
    rconfig = rule.get("rule_config") or {}
    field = rconfig.get("field", "")

    if rtype == "MIN_VALUE":
        min_val = rconfig.get("minimum", 0)
        if field == "academic_score":
            return f"Academic score ≥ {min_val}%"
        if field == "previous_score":
            return f"Previous score ≥ {min_val}%"
        if field == "attendance":
            return f"Attendance record ≥ {min_val}%"
        return f"{field.replace('_', ' ').capitalize()} ≥ {min_val}"

    if rtype == "MAX_VALUE":
        max_val = rconfig.get("maximum", 0)
        if field == "annual_income":
            return f"Annual family income ≤ ₹{int(max_val):,}"
        return f"{field.replace('_', ' ').capitalize()} ≤ {max_val}"

    if rtype == "DOCUMENT_VERIFICATION":
        return "Required document verification"

    return rule.get("rule_name") or rule.get("rule_code") or "Eligibility requirement"


def build_scheme_verification_summary(
    required_documents: List[str],
    uploaded_docs: List[Dict[str, Any]],
    scheme_name: str,
) -> Dict[str, Any]:
    """
    Construct an in-memory document verification summary for a specific scholarship scheme
    given the applicant's uploaded documents.
    """
    docs_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for doc in uploaded_docs:
        dtype = doc.get("document_type")
        if dtype:
            docs_by_type.setdefault(dtype, []).append(doc)

    summary: Dict[str, Any] = {
        "scheme_name": scheme_name,
        "required_documents": list(required_documents),
        "documents": {},
        "missing_documents": [],
        "mismatched_documents": [],
        "needs_review_documents": [],
    }

    verified_count = 0
    for req_type in required_documents:
        matching = docs_by_type.get(req_type, [])
        if not matching:
            summary["documents"][req_type] = {"status": "MISSING"}
            summary["missing_documents"].append(req_type)
            continue

        verified_docs = [d for d in matching if d.get("verification_status") == "VERIFIED"]
        if verified_docs:
            doc = verified_docs[-1]
            status = "VERIFIED"
            verified_count += 1
        else:
            doc = matching[-1]
            status = doc.get("verification_status") or "PENDING"
            if status in ("MISMATCH", "REJECTED"):
                summary["mismatched_documents"].append(req_type)
            else:
                summary["needs_review_documents"].append(req_type)

        summary["documents"][req_type] = {
            "status": status,
            "file_name": doc.get("file_name"),
            "verification_score": doc.get("verification_score"),
        }

    if verified_count == len(required_documents) and len(required_documents) > 0:
        summary["overall_status"] = "VERIFIED"
    elif summary["missing_documents"] and verified_count == 0:
        summary["overall_status"] = "INCOMPLETE"
    else:
        summary["overall_status"] = "NEEDS_REVIEW"

    return summary


def get_applicant_all_documents(applicant_id: str) -> List[Dict[str, Any]]:
    """Retrieve all uploaded documents across all applications for the student."""
    apps = get_applications_by_applicant(applicant_id) or []
    if not apps:
        return []
    app_ids = [a.get("id") for a in apps if a.get("id")]
    if not app_ids:
        return []
    all_docs: List[Dict[str, Any]] = []
    seen_ids = set()
    for i in range(0, len(app_ids), 50):
        chunk = app_ids[i:i+50]
        try:
            res = (
                supabase
                .table("documents")
                .select("*")
                .in_("application_id", chunk)
                .order("created_at")
                .execute()
            )
            for d in (res.data or []):
                did = d.get("id")
                if did and did not in seen_ids:
                    seen_ids.add(did)
                    all_docs.append(d)
        except Exception:
            pass
    return all_docs


def evaluate_student_eligibility(
    applicant_id: str,
    candidate_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate eligibility for all active scholarship schemes for an applicant.

    Args:
        applicant_id: UUID of the authenticated student.
        candidate_data: Optional candidate values for pre-submission checks
                        (e.g. academic_score, annual_income). Evaluated entirely in-memory.

    Returns:
        Structured Copilot report with eligibility categories, match percentages,
        and rule-grounded explanations.
    """
    profile = get_applicant_profile(applicant_id)
    if not profile:
        raise ValueError(f"Student profile not found for ID: {applicant_id}")

    # 1. Determine student application baseline data and documents
    existing_apps = get_applications_by_applicant(applicant_id) or []
    latest_app = existing_apps[0] if existing_apps else None
    uploaded_docs = get_applicant_all_documents(applicant_id)

    # Assemble working applicant data (in-memory candidate values take precedence)
    app_data: Dict[str, Any] = {
        "academic_score": None,
        "previous_score": None,
        "attendance": None,
        "annual_income": None,
        "application_category": "GENERAL",
    }

    if latest_app:
        for k in ("academic_score", "previous_score", "attendance", "annual_income", "application_category"):
            if latest_app.get(k) is not None:
                app_data[k] = latest_app.get(k)

    if candidate_data:
        for k in ("academic_score", "previous_score", "attendance", "annual_income", "application_category"):
            if k in candidate_data and candidate_data[k] is not None:
                if k in ("academic_score", "previous_score", "attendance", "annual_income"):
                    try:
                        app_data[k] = float(candidate_data[k])
                    except (ValueError, TypeError):
                        pass
                else:
                    app_data[k] = str(candidate_data[k]).strip().upper()

    # 2. Fetch all active scholarship schemes from Supabase
    schemes_res = (
        supabase
        .table("scholarship_schemes")
        .select("id, scheme_code, scheme_name, description, required_documents, is_active")
        .eq("is_active", True)
        .order("scheme_name")
        .execute()
    )
    active_schemes = schemes_res.data or []

    # 3. Evaluate each active scheme
    evaluated_scholarships: List[Dict[str, Any]] = []

    for scheme in active_schemes:
        scheme_id = scheme["id"]
        scheme_code = scheme.get("scheme_code") or "SCHOLARSHIP"
        scheme_name = scheme.get("scheme_name") or "Scholarship"
        required_docs = scheme.get("required_documents") or []

        # Load active rules from Supabase
        rules = get_scholarship_rules(scheme_id)

        # Build in-memory verification summary for this scheme
        v_summary = build_scheme_verification_summary(required_docs, uploaded_docs, scheme_name)

        # Evaluate rules using existing pure evaluator
        eval_result = evaluate_rules_for_data(
            rules=rules,
            application_data=app_data,
            verification_summary=v_summary,
            application_id=latest_app.get("id") if latest_app else None,
            scholarship_scheme_id=scheme_id,
        )

        passed_rules = eval_result.get("passed_rules", [])
        failed_rules = eval_result.get("failed_rules", [])
        total_rules = eval_result.get("total_rules", 0)

        # Separate numeric/substantive rules from document rules
        numeric_failed = [r for r in failed_rules if r.get("rule_type") != "DOCUMENT_VERIFICATION"]
        doc_failed = [r for r in failed_rules if r.get("rule_type") == "DOCUMENT_VERIFICATION"]

        # Calculate exact Match Percentage = (passed_rules / total_rules) * 100
        match_percentage = round((len(passed_rules) / total_rules) * 100) if total_rules > 0 else 0

        # ---- Apply Strict Priority Rules ----
        # 1. If any numeric/substantive rule fails -> NOT_ELIGIBLE
        # 2. If all numeric rules pass but required documents are not verified -> NEEDS_VERIFICATION
        # 3. If all criteria and required documents pass -> ELIGIBLE
        if len(numeric_failed) > 0:
            status = "NOT_ELIGIBLE"
        elif len(doc_failed) > 0 or v_summary.get("overall_status") != "VERIFIED":
            status = "NEEDS_VERIFICATION"
        else:
            status = "ELIGIBLE"

        # Build detailed criteria lists for transparency
        passed_criteria: List[Dict[str, Any]] = []
        for r in passed_rules:
            passed_criteria.append({
                "rule_code": r["rule_code"],
                "rule_name": r["rule_name"],
                "criteria": _format_rule_title(r),
                "message": r.get("message", "Requirement satisfied."),
                "status": "PASS",
            })

        failed_criteria: List[Dict[str, Any]] = []
        for r in numeric_failed:
            failed_criteria.append({
                "rule_code": r["rule_code"],
                "rule_name": r["rule_name"],
                "criteria": _format_rule_title(r),
                "message": r.get("message", "Criteria threshold not met."),
                "actual_value": r.get("details", {}).get("actual_value"),
                "required_value": r.get("details", {}).get("required_value"),
                "status": "FAIL",
            })

        # Verification items breakdown
        verification_items: List[Dict[str, Any]] = []
        for dtype in required_docs:
            dinfo = v_summary["documents"].get(dtype, {})
            dstatus = dinfo.get("status", "MISSING")
            verification_items.append({
                "document_type": dtype,
                "document_label": DOC_TYPE_LABELS.get(dtype, dtype.replace("_", " ").title()),
                "status": dstatus,
                "verified": dstatus == "VERIFIED",
            })

        # Generate rule-grounded, traceable explanation
        explanation = ""
        next_action: Optional[str] = None

        if status == "ELIGIBLE":
            explanation = "You currently satisfy all configured academic, financial, and document verification criteria for this scholarship."
            next_action = "You meet all configured requirements and are eligible to apply."
        elif status == "NEEDS_VERIFICATION":
            missing_names = [
                DOC_TYPE_LABELS.get(d, d.replace("_", " ").title())
                for d in v_summary.get("missing_documents", [])
            ]
            unverified_names = [
                DOC_TYPE_LABELS.get(d, d.replace("_", " ").title())
                for d in (v_summary.get("needs_review_documents", []) + v_summary.get("mismatched_documents", []))
            ]
            all_pending = missing_names + unverified_names
            pending_str = ", ".join(all_pending) if all_pending else "required documents"

            explanation = (
                f"You satisfy the configured academic and financial criteria, but required verification "
                f"({pending_str}) is incomplete or pending."
            )
            next_action = f"Upload and complete verification for: {pending_str}."
        else: # NOT_ELIGIBLE
            failed_msgs = [r.get("message", "Criteria not met") for r in numeric_failed]
            explanation = "Does not currently meet the configured criteria: " + "; ".join(failed_msgs)
            next_action = "Review the requirements for this scholarship or consider applying for an alternative scheme with matching eligibility."

        evaluated_scholarships.append({
            "scheme_id": scheme_id,
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "description": scheme.get("description") or "",
            "status": status,
            "match_percentage": match_percentage,
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "verification_items": verification_items,
            "required_documents": [
                {
                    "type": dt,
                    "label": DOC_TYPE_LABELS.get(dt, dt.replace("_", " ").title()),
                }
                for dt in required_docs
            ],
            "document_status": v_summary.get("overall_status") or "INCOMPLETE",
            "explanation": explanation,
            "next_action": next_action,
            "rules_count": {
                "total": total_rules,
                "passed": len(passed_rules),
                "failed": len(failed_rules),
            },
        })

    # Sort scholarships: ELIGIBLE first, then NEEDS_VERIFICATION, then NOT_ELIGIBLE
    category_order = {"ELIGIBLE": 0, "NEEDS_VERIFICATION": 1, "NOT_ELIGIBLE": 2}
    evaluated_scholarships.sort(
        key=lambda s: (category_order.get(s["status"], 99), -s["match_percentage"])
    )

    eligible_count = sum(1 for s in evaluated_scholarships if s["status"] == "ELIGIBLE")
    needs_verif_count = sum(1 for s in evaluated_scholarships if s["status"] == "NEEDS_VERIFICATION")
    not_eligible_count = sum(1 for s in evaluated_scholarships if s["status"] == "NOT_ELIGIBLE")

    return {
        "success": True,
        "student": {
            "id": profile.get("id"),
            "name": profile.get("full_name") or "Student",
            "phone": profile.get("phone"),
        },
        "working_data": {
            "academic_score": app_data.get("academic_score"),
            "previous_score": app_data.get("previous_score"),
            "attendance": app_data.get("attendance"),
            "annual_income": app_data.get("annual_income"),
            "application_category": app_data.get("application_category"),
            "has_existing_application": latest_app is not None,
            "application_id": latest_app.get("id") if latest_app else None,
            "uploaded_documents_count": len(uploaded_docs),
        },
        "counts": {
            "total_schemes": len(evaluated_scholarships),
            "eligible": eligible_count,
            "needs_verification": needs_verif_count,
            "not_eligible": not_eligible_count,
        },
        "scholarships": evaluated_scholarships,
    }
