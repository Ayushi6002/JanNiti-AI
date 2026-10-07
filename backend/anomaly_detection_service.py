"""
anomaly_detection_service.py
----------------------------
Feature 3: Document Fraud & Anomaly Detection Service for Jan Niti AI.

Provides rule-based document integrity, consistency, completeness, and duplicate
detection. Strictly advisory: flags anomalies and routes safely to HUMAN_REVIEW.
Never automatically rejects an application or claims legal fraud.

Terminology used:
- CLEAN
- ANOMALY_DETECTED
- NEEDS_HUMAN_REVIEW
"""

import hashlib
import json
import logging
import re
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.supabase_client import supabase
    from backend.application_service import (
        get_application_verification_data,
        get_applicant_profile,
    )
    from backend.verification_service import (
        generate_verification_summary,
        get_application_documents,
        get_required_documents_for_application,
    )
    from backend.audit_service import log_audit
    from backend.document_extractor import normalize_category
    from backend import db
except ImportError:
    from supabase_client import supabase
    from application_service import (
        get_application_verification_data,
        get_applicant_profile,
    )
    from verification_service import (
        generate_verification_summary,
        get_application_documents,
        get_required_documents_for_application,
    )
    from audit_service import log_audit
    from document_extractor import normalize_category
    import db


logger = logging.getLogger(__name__)


class ApplicationNotFoundError(Exception):
    """Raised when an application is not found."""
    pass


class ForbiddenAnomalyAccessError(Exception):
    """Raised when an applicant attempts to access anomaly data of another applicant."""
    pass


def calculate_content_hash(data: bytes | str) -> str:
    """Calculate SHA-256 content hash of document bytes or text."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _get_document_hash(doc: Dict[str, Any]) -> Optional[str]:
    """Extract or calculate content hash from document data or text."""
    if not isinstance(doc, dict):
        return None
    extracted = doc.get("extracted_data") or {}
    if extracted.get("content_hash"):
        return str(extracted["content_hash"])
    text = (doc.get("extracted_text") or "").strip()
    if text:
        return calculate_content_hash(text)
    return None


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


def detect_field_inconsistencies(
    application_data: Dict[str, Any],
    documents: List[Dict[str, Any]],
    profile_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Detect mismatches between application form values and extracted document data.
    """
    anomalies: List[Dict[str, Any]] = []
    profile_name = (profile_data.get("full_name") or "").strip().lower()

    for doc in documents:
        doc_type = doc.get("document_type")
        doc_id = doc.get("id")
        file_name = doc.get("file_name", f"{doc_type}.pdf")
        extracted = doc.get("extracted_data") or {}

        # 1. Student Name check against applicant profile
        doc_student_name = extracted.get("student_name")
        if doc_student_name and profile_name:
            clean_doc_name = str(doc_student_name).strip().lower()
            if clean_doc_name != profile_name:
                anomalies.append({
                    "type": "NAME_MISMATCH",
                    "category": "FIELD_INCONSISTENCY",
                    "field": "student_name",
                    "severity": "HIGH",
                    "score_weight": 50.0,
                    "document_id": doc_id,
                    "document_type": doc_type,
                    "file_name": file_name,
                    "message": (
                        f"Student name on document '{doc_type}' ('{doc_student_name}') "
                        f"does not match applicant profile name ('{profile_data.get('full_name')}')."
                    ),
                    "details": {
                        "document_value": doc_student_name,
                        "profile_value": profile_data.get("full_name"),
                    },
                })

        # 2. Marksheet academic & previous score checks
        if doc_type == "marksheet":
            doc_acad = extracted.get("academic_score")
            app_acad = application_data.get("academic_score")
            if doc_acad is not None and app_acad is not None:
                try:
                    if abs(float(doc_acad) - float(app_acad)) > 0.01:
                        anomalies.append({
                            "type": "FIELD_MISMATCH",
                            "category": "FIELD_INCONSISTENCY",
                            "field": "academic_score",
                            "severity": "HIGH",
                            "score_weight": 45.0,
                            "document_id": doc_id,
                            "document_type": doc_type,
                            "file_name": file_name,
                            "message": (
                                f"Academic score differs between application ({app_acad}) "
                                f"and marksheet ({doc_acad})."
                            ),
                            "details": {
                                "application_value": app_acad,
                                "document_value": doc_acad,
                                "discrepancy": round(float(app_acad) - float(doc_acad), 2),
                            },
                        })
                except (ValueError, TypeError):
                    pass

            doc_prev = extracted.get("previous_score")
            app_prev = application_data.get("previous_score")
            if doc_prev is not None and app_prev is not None:
                try:
                    if abs(float(doc_prev) - float(app_prev)) > 0.01:
                        anomalies.append({
                            "type": "FIELD_MISMATCH",
                            "category": "FIELD_INCONSISTENCY",
                            "field": "previous_score",
                            "severity": "HIGH",
                            "score_weight": 40.0,
                            "document_id": doc_id,
                            "document_type": doc_type,
                            "file_name": file_name,
                            "message": (
                                f"Previous score differs between application ({app_prev}) "
                                f"and marksheet ({doc_prev})."
                            ),
                            "details": {
                                "application_value": app_prev,
                                "document_value": doc_prev,
                                "discrepancy": round(float(app_prev) - float(doc_prev), 2),
                            },
                        })
                except (ValueError, TypeError):
                    pass

        # 3. Income Certificate annual_income check
        elif doc_type == "income_certificate":
            doc_inc = extracted.get("annual_income")
            app_inc = application_data.get("annual_income")
            if doc_inc is not None and app_inc is not None:
                try:
                    if abs(float(doc_inc) - float(app_inc)) > 0.01:
                        anomalies.append({
                            "type": "FIELD_MISMATCH",
                            "category": "FIELD_INCONSISTENCY",
                            "field": "annual_income",
                            "severity": "HIGH",
                            "score_weight": 45.0,
                            "document_id": doc_id,
                            "document_type": doc_type,
                            "file_name": file_name,
                            "message": (
                                f"Annual income differs between application (Rs. {float(app_inc):,.0f}) "
                                f"and income certificate (Rs. {float(doc_inc):,.0f})."
                            ),
                            "details": {
                                "application_value": app_inc,
                                "document_value": doc_inc,
                                "discrepancy": round(float(app_inc) - float(doc_inc), 2),
                            },
                        })
                except (ValueError, TypeError):
                    pass

        # 4. Category Certificate category check
        elif doc_type == "category_certificate":
            doc_cat = extracted.get("category")
            app_cat = application_data.get("application_category")
            if doc_cat and app_cat:
                norm_doc = normalize_category(doc_cat)
                norm_app = normalize_category(app_cat)
                if norm_doc != norm_app:
                    anomalies.append({
                        "type": "FIELD_MISMATCH",
                        "category": "FIELD_INCONSISTENCY",
                        "field": "application_category",
                        "severity": "HIGH",
                        "score_weight": 40.0,
                        "document_id": doc_id,
                        "document_type": doc_type,
                        "file_name": file_name,
                        "message": (
                            f"Application category ('{app_cat}') does not match "
                            f"category certificate ('{doc_cat}')."
                        ),
                        "details": {
                            "application_value": app_cat,
                            "document_value": doc_cat,
                            "normalized_application": norm_app,
                            "normalized_document": norm_doc,
                        },
                    })

    return anomalies


def detect_cross_document_anomalies(
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compare information across multiple uploaded documents of the applicant.
    """
    anomalies: List[Dict[str, Any]] = []

    # Cross-document student name comparison
    names_by_doc: Dict[str, str] = {}
    for doc in documents:
        extracted = doc.get("extracted_data") or {}
        name = extracted.get("student_name")
        if name and str(name).strip():
            names_by_doc[doc.get("document_type")] = str(name).strip()

    unique_names = set(n.lower() for n in names_by_doc.values())
    if len(unique_names) > 1:
        doc_details = [f"{dtype}: '{name}'" for dtype, name in names_by_doc.items()]
        anomalies.append({
            "type": "CROSS_DOCUMENT_NAME_MISMATCH",
            "category": "CROSS_DOCUMENT_INCONSISTENCY",
            "field": "student_name",
            "severity": "HIGH",
            "score_weight": 45.0,
            "document_id": None,
            "document_type": "multiple",
            "message": (
                f"Conflicting student names detected across uploaded documents: {', '.join(doc_details)}."
            ),
            "details": names_by_doc,
        })

    # Internal duplication: same file uploaded for multiple distinct document types
    hashes_seen: Dict[str, str] = {}
    for doc in documents:
        chash = _get_document_hash(doc)
        dtype = doc.get("document_type")
        if chash:
            if chash in hashes_seen:
                prev_dtype = hashes_seen[chash]
                anomalies.append({
                    "type": "DUPLICATE_FILE_IN_APPLICATION",
                    "category": "SUSPICIOUS_DUPLICATION",
                    "field": "document_file",
                    "severity": "HIGH",
                    "score_weight": 45.0,
                    "document_id": doc.get("id"),
                    "document_type": dtype,
                    "file_name": doc.get("file_name"),
                    "message": (
                        f"The identical document file was uploaded for both '{prev_dtype}' and '{dtype}'."
                    ),
                    "details": {
                        "document_type_1": prev_dtype,
                        "document_type_2": dtype,
                        "content_hash": chash,
                    },
                })
            else:
                hashes_seen[chash] = dtype

    return anomalies


def detect_completeness_anomalies(
    required_documents: List[str],
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Detect missing required documents, unreadable text, or absent critical fields.
    """
    anomalies: List[Dict[str, Any]] = []
    uploaded_types = {d.get("document_type"): d for d in documents}

    # 1. Missing required documents
    for req_type in required_documents:
        if req_type not in uploaded_types:
            anomalies.append({
                "type": "MISSING_REQUIRED_DOCUMENT",
                "category": "DOCUMENT_COMPLETENESS",
                "field": req_type,
                "severity": "MEDIUM",
                "score_weight": 25.0,
                "document_id": None,
                "document_type": req_type,
                "file_name": None,
                "message": f"Required document '{req_type}' is missing from the application.",
                "details": {"required_document": req_type},
            })

    # 2. Check each uploaded document for empty text and critical expected fields
    for doc in documents:
        dtype = doc.get("document_type")
        doc_id = doc.get("id")
        file_name = doc.get("file_name", f"{dtype}.pdf")
        text = doc.get("extracted_text") or ""
        extracted = doc.get("extracted_data") or {}

        # Unreadable or blank document
        if not text.strip():
            anomalies.append({
                "type": "EMPTY_DOCUMENT_TEXT",
                "category": "DOCUMENT_QUALITY",
                "field": dtype,
                "severity": "HIGH",
                "score_weight": 35.0,
                "document_id": doc_id,
                "document_type": dtype,
                "file_name": file_name,
                "message": (
                    f"Uploaded document '{dtype}' ({file_name}) contains no extractable text "
                    f"or appears unreadable."
                ),
                "details": {"file_name": file_name},
            })
            continue

        # Missing expected fields by document type
        missing_fields = []
        if dtype == "marksheet":
            if extracted.get("academic_score") is None:
                missing_fields.append("academic_score")
            if extracted.get("student_name") is None:
                missing_fields.append("student_name")
        elif dtype == "income_certificate":
            if extracted.get("annual_income") is None:
                missing_fields.append("annual_income")
            if extracted.get("student_name") is None:
                missing_fields.append("student_name")
        elif dtype == "id_proof":
            if not extracted.get("id_number"):
                missing_fields.append("id_number")
            if extracted.get("student_name") is None:
                missing_fields.append("student_name")
        elif dtype == "category_certificate":
            if not extracted.get("category"):
                missing_fields.append("category")
            if extracted.get("student_name") is None:
                missing_fields.append("student_name")

        if missing_fields:
            anomalies.append({
                "type": "MISSING_CRITICAL_DOCUMENT_FIELDS",
                "category": "DOCUMENT_COMPLETENESS",
                "field": ", ".join(missing_fields),
                "severity": "MEDIUM",
                "score_weight": 25.0,
                "document_id": doc_id,
                "document_type": dtype,
                "file_name": file_name,
                "message": (
                    f"Document '{dtype}' is missing critical expected information: "
                    f"{', '.join(missing_fields)}."
                ),
                "details": {
                    "missing_fields": missing_fields,
                    "extracted_data": extracted,
                },
            })

    return anomalies


def detect_duplicate_document_reuse(
    application_id: str,
    applicant_id: str,
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Detect if the same document content hash has been reused across different applications.
    Prioritizes cross-applicant document reuse (which indicates certificate sharing/fraud).
    """
    anomalies: List[Dict[str, Any]] = []

    for doc in documents:
        chash = _get_document_hash(doc)
        extracted = doc.get("extracted_data") or {}
        doc_id = doc.get("id")
        doc_type = doc.get("document_type")
        file_name = doc.get("file_name", f"{doc_type}.pdf")

        if not chash:
            continue

        try:
            # Query documents in other applications that have the same content_hash
            dup_res = (
                supabase
                .table("documents")
                .select("""
                    id,
                    application_id,
                    document_type,
                    file_name,
                    extracted_text,
                    extracted_data,
                    applications (
                        id,
                        application_number,
                        applicant_id
                    )
                """)
                .neq("application_id", application_id)
                .execute()
            )
            candidates = dup_res.data or []

            for other_doc in candidates:
                other_hash = _get_document_hash(other_doc)
                if not other_hash or other_hash != chash:
                    continue

                other_extracted = other_doc.get("extracted_data") or {}
                other_app = other_doc.get("applications") or {}
                other_applicant_id = other_app.get("applicant_id")
                other_app_id = other_app.get("id") or other_doc.get("application_id")
                other_app_num = other_app.get("application_number", "Unknown")

                # Cross-applicant duplication is a high-severity anomaly
                if other_applicant_id and other_applicant_id != applicant_id:
                    anomalies.append({
                        "type": "DUPLICATE_DOCUMENT",
                        "category": "SUSPICIOUS_DUPLICATION",
                        "field": "document_hash",
                        "severity": "HIGH",
                        "score_weight": 50.0,
                        "document_id": doc_id,
                        "document_type": doc_type,
                        "file_name": file_name,
                        "message": (
                            f"Document '{file_name}' appears to be identical to a document "
                            f"previously submitted in application '{other_app_num}' by another applicant."
                        ),
                        "details": {
                            "reused_document_id": other_doc.get("id"),
                            "other_application_id": other_app_id,
                            "other_application_number": other_app_num,
                            "other_applicant_id": other_applicant_id,
                            "content_hash": chash,
                        },
                    })
                    break  # Flag once per document
                elif other_app_id and other_app_id != application_id:
                    # Same applicant reuse across applications
                    # Can still be noted if student names or critical metadata differ
                    other_name = other_extracted.get("student_name")
                    curr_name = extracted.get("student_name")
                    if other_name and curr_name and str(other_name).strip().lower() != str(curr_name).strip().lower():
                        anomalies.append({
                            "type": "DUPLICATE_DOCUMENT",
                            "category": "SUSPICIOUS_DUPLICATION",
                            "field": "document_hash",
                            "severity": "HIGH",
                            "score_weight": 50.0,
                            "document_id": doc_id,
                            "document_type": doc_type,
                            "file_name": file_name,
                            "message": (
                                f"Document '{file_name}' has matching content with application "
                                f"'{other_app_num}' but has conflicting student identities."
                            ),
                            "details": {
                                "other_application_id": other_app_id,
                                "other_application_number": other_app_num,
                                "content_hash": chash,
                            },
                        })
                        break
        except Exception as exc:
            logger.warning(f"Error querying duplicate documents in Supabase: {exc}")

    return anomalies


def detect_temporal_anomalies(
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Detect expired certificates or impossible date ordering where dates are present.
    """
    anomalies: List[Dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for doc in documents:
        text = doc.get("extracted_text") or ""
        doc_type = doc.get("document_type")
        doc_id = doc.get("id")
        file_name = doc.get("file_name", f"{doc_type}.pdf")

        # Check extracted_data first if dates were extracted
        extracted = doc.get("extracted_data") or {}
        issue_date = None
        expiry_date = None

        if extracted.get("issue_date"):
            issue_date = _parse_date(extracted["issue_date"])
        if extracted.get("expiry_date"):
            expiry_date = _parse_date(extracted["expiry_date"])

        # Search for date patterns in text if not present in extracted_data
        if not issue_date and text:
            issue_match = re.search(
                r"(?:Issue\s*Date|Date\s*of\s*Issue)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{2}-[0-9]{2}-[0-9]{4})",
                text,
                re.IGNORECASE,
            )
            if issue_match:
                issue_date = _parse_date(issue_match.group(1))

        if not expiry_date and text:
            expiry_match = re.search(
                r"(?:Expiry\s*Date|Valid\s*Till|Valid\s*Upto|Expiry)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{2}-[0-9]{2}-[0-9]{4})",
                text,
                re.IGNORECASE,
            )
            if expiry_match:
                expiry_date = _parse_date(expiry_match.group(1))

        if issue_date and issue_date > today:
            anomalies.append({
                "type": "FUTURE_ISSUE_DATE",
                "category": "TEMPORAL_ANOMALY",
                "field": "issue_date",
                "severity": "HIGH",
                "score_weight": 35.0,
                "document_id": doc_id,
                "document_type": doc_type,
                "file_name": file_name,
                "message": f"Document '{doc_type}' indicates an issue date in the future ({issue_date}).",
                "details": {"issue_date": str(issue_date), "current_date": str(today)},
            })

        if expiry_date and expiry_date < today:
            anomalies.append({
                "type": "EXPIRED_DOCUMENT",
                "category": "TEMPORAL_ANOMALY",
                "field": "expiry_date",
                "severity": "MEDIUM",
                "score_weight": 25.0,
                "document_id": doc_id,
                "document_type": doc_type,
                "file_name": file_name,
                "message": f"Document '{doc_type}' expired on {expiry_date}.",
                "details": {"expiry_date": str(expiry_date), "current_date": str(today)},
            })

        if issue_date and expiry_date and expiry_date < issue_date:
            anomalies.append({
                "type": "INVALID_DATE_ORDER",
                "category": "TEMPORAL_ANOMALY",
                "field": "dates",
                "severity": "HIGH",
                "score_weight": 35.0,
                "document_id": doc_id,
                "document_type": doc_type,
                "file_name": file_name,
                "message": (
                    f"Document '{doc_type}' expiry date ({expiry_date}) "
                    f"precedes issue date ({issue_date})."
                ),
                "details": {
                    "issue_date": str(issue_date),
                    "expiry_date": str(expiry_date),
                },
            })

    return anomalies


def compute_anomaly_score_and_risk(
    reasons: List[Dict[str, Any]]
) -> Tuple[float, str, str, str]:
    """
    Computes overall anomaly_score (0-100), risk_level (LOW, MEDIUM, HIGH),
    status (CLEAN, ANOMALY_DETECTED), and recommended_action.
    """
    if not reasons:
        return 0.0, "LOW", "CLEAN", "PROCEED"

    raw_score = sum(float(r.get("score_weight", 20.0)) for r in reasons)
    final_score = round(min(100.0, max(0.0, raw_score)), 1)

    has_high = any(r.get("severity") == "HIGH" for r in reasons)

    if final_score >= 50.0 or has_high:
        risk_level = "HIGH"
        status = "ANOMALY_DETECTED"
        recommended_action = "NEEDS_HUMAN_REVIEW"
    elif final_score >= 20.0:
        risk_level = "MEDIUM"
        status = "ANOMALY_DETECTED"
        recommended_action = "NEEDS_HUMAN_REVIEW"
    else:
        risk_level = "LOW"
        status = "CLEAN"
        recommended_action = "PROCEED"

    return final_score, risk_level, status, recommended_action


def analyze_application_anomalies(
    application_id: str,
    applicant_id: Optional[str] = None,
    verification_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Core entrypoint to evaluate document anomalies for an application.
    Deterministic, advisory, and strictly read-only during analysis.
    """
    # 1. Fetch application verification data
    try:
        app_data = get_application_verification_data(application_id)
    except Exception as exc:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.") from exc

    if not app_data:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

    actual_applicant_id = app_data.get("applicant_id") or applicant_id

    # 2. Fetch applicant profile
    profile_data = {}
    if actual_applicant_id:
        try:
            profile_data = get_applicant_profile(actual_applicant_id) or {}
        except Exception as exc:
            logger.warning(f"Could not load applicant profile for {actual_applicant_id}: {exc}")

    # 3. Fetch required documents
    required_docs = []
    try:
        _, required_docs = get_required_documents_for_application(application_id)
    except Exception:
        if verification_summary:
            required_docs = verification_summary.get("required_documents") or []

    # 4. Fetch uploaded documents (with extracted_text for anomaly verification)
    documents = []
    try:
        doc_res = (
            supabase
            .table("documents")
            .select("""
                id,
                application_id,
                document_type,
                file_name,
                storage_path,
                verification_status,
                verification_score,
                extracted_text,
                extracted_data,
                mismatch_details,
                verified_at,
                created_at
            """)
            .eq("application_id", application_id)
            .order("created_at")
            .execute()
        )
        documents = doc_res.data or []
    except Exception as exc:
        logger.warning(f"Could not load full document details from Supabase: {exc}")

    if not documents:
        documents = get_application_documents(application_id)

    # 5. Execute all anomaly detection rules
    all_reasons: List[Dict[str, Any]] = []

    # A. Field Inconsistencies (Application vs Document, Profile vs Document)
    all_reasons.extend(detect_field_inconsistencies(app_data, documents, profile_data))

    # B. Cross-Document Inconsistencies
    all_reasons.extend(detect_cross_document_anomalies(documents))

    # C. Document Completeness & Quality
    all_reasons.extend(detect_completeness_anomalies(required_docs, documents))

    # D. Suspicious Duplication
    all_reasons.extend(detect_duplicate_document_reuse(application_id, actual_applicant_id, documents))

    # E. Temporal & Expiry Anomalies
    all_reasons.extend(detect_temporal_anomalies(documents))

    # 6. Compute scores and risk
    anomaly_score, risk_level, status, action = compute_anomaly_score_and_risk(all_reasons)

    # Clean formatted reasons for presentation
    clean_reasons = []
    for r in all_reasons:
        clean_reasons.append({
            "type": r.get("type"),
            "category": r.get("category"),
            "field": r.get("field"),
            "severity": r.get("severity"),
            "score_weight": r.get("score_weight"),
            "score": r.get("score_weight"),
            "document_id": r.get("document_id"),
            "document_type": r.get("document_type"),
            "file_name": r.get("file_name"),
            "message": r.get("message"),
            "details": r.get("details"),
        })

    detected_at = datetime.now(timezone.utc).isoformat()

    if status == "CLEAN":
        summary_msg = "No suspicious document anomalies detected. Application is consistent."
    else:
        summary_msg = (
            f"Detected {len(clean_reasons)} anomaly/inconsistency item(s) "
            f"with {risk_level} risk level. Routed to human reviewer for review."
        )

    return {
        "application_id": application_id,
        "applicant_id": actual_applicant_id,
        "status": status,
        "risk_level": risk_level,
        "anomaly_score": anomaly_score,
        "recommended_action": action,
        "summary": summary_msg,
        "anomalies_count": len(clean_reasons),
        "reasons": clean_reasons,
        "detected_at": detected_at,
        "is_advisory": True,
        "human_review_required": status == "ANOMALY_DETECTED",
    }


def record_anomaly_assessment(
    application_id: str,
    assessment: Dict[str, Any],
    actor_id: Optional[str] = None,
) -> None:
    """
    Persists anomaly assessment:
    1. Saves individual findings to local SQLite 'document_anomalies' (idempotent).
    2. Logs structured audit event to Supabase 'audit_logs'.
    """
    try:
        # 1. Save to SQLite document_anomalies
        db.save_document_anomalies(application_id, assessment.get("reasons") or [])
    except Exception as exc:
        logger.error(f"Error saving document anomalies to SQLite for {application_id}: {exc}")

    try:
        # 2. Log to Supabase audit_logs
        action = "ANOMALY_DETECTED" if assessment.get("status") == "ANOMALY_DETECTED" else "ANOMALY_CHECK_PASSED"
        log_audit(
            application_id=application_id,
            action=action,
            actor_id=actor_id,
            old_value=None,
            new_value={
                "status": assessment.get("status"),
                "risk_level": assessment.get("risk_level"),
                "anomaly_score": assessment.get("anomaly_score"),
                "recommended_action": assessment.get("recommended_action"),
                "summary": assessment.get("summary"),
                "anomalies_count": assessment.get("anomalies_count"),
                "reasons": assessment.get("reasons") or [],
                "detected_at": assessment.get("detected_at"),
                "human_review_required": assessment.get("human_review_required", assessment.get("status") == "ANOMALY_DETECTED"),
                "is_advisory": True,
            },
            reason=assessment.get("summary"),
            entity_type="document_anomalies",
            entity_id=application_id,
        )
    except Exception as exc:
        logger.warning(f"Could not write anomaly audit log to Supabase: {exc}")


def analyze_and_record_application_anomalies(
    application_id: str,
    applicant_id: Optional[str] = None,
    verification_summary: Optional[Dict[str, Any]] = None,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Complete workflow: run analysis and persist findings + audit log.
    Used by the application processing pipeline.
    """
    assessment = analyze_application_anomalies(
        application_id=application_id,
        applicant_id=applicant_id,
        verification_summary=verification_summary,
    )
    record_anomaly_assessment(application_id, assessment, actor_id=actor_id)
    return assessment


def get_application_anomalies(
    application_id: str,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Retrieves the anomaly assessment for an application with role-based authorization.
    - Applicant: only allowed for their own application.
    - Admin: allowed for any application.
    """
    # 1. Fetch application row from Supabase
    try:
        app_res = (
            supabase
            .table("applications")
            .select("id, application_number, applicant_id, status")
            .eq("id", application_id)
            .single()
            .execute()
        )
        app_row = app_res.data
    except Exception as exc:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.") from exc

    if not app_row:
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

    # 2. Authorization check
    user_role = (current_user.get("role") or "").lower().strip()
    user_id = current_user.get("id")

    if user_role == "applicant":
        if app_row.get("applicant_id") != user_id:
            raise ForbiddenAnomalyAccessError(
                "Access forbidden: You are only authorized to access anomaly details for your own application."
            )
    elif user_role == "admin":
        pass  # Admin authorized
    else:
        raise ForbiddenAnomalyAccessError("Access forbidden: Unauthorized role.")

    # 3. Analyze fresh to ensure accuracy and return
    assessment = analyze_application_anomalies(application_id, app_row.get("applicant_id"))

    # Also fetch persisted records from SQLite or Supabase audit_logs
    persisted_records = db.get_document_anomalies_for_app(application_id)
    if not persisted_records:
        try:
            audit_res = (
                supabase
                .table("audit_logs")
                .select("id, action, new_value, created_at")
                .eq("application_id", application_id)
                .eq("entity_type", "document_anomalies")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if audit_res.data and isinstance(audit_res.data[0].get("new_value"), dict):
                saved_reasons = audit_res.data[0]["new_value"].get("reasons") or []
                persisted_records = [
                    {
                        "id": f"supabase-{audit_res.data[0]['id']}-{i}",
                        "application_id": application_id,
                        "document_id": r.get("document_id"),
                        "anomaly_type": r.get("type"),
                        "severity": r.get("severity"),
                        "anomaly_score": r.get("score_weight", r.get("score", 0.0)),
                        "status": "DETECTED",
                        "reason": r.get("message"),
                        "details": r.get("details"),
                        "detected_at": audit_res.data[0]["created_at"],
                    }
                    for i, r in enumerate(saved_reasons)
                ]
        except Exception as exc:
            logger.debug(f"Could not fetch audit log for anomaly records: {exc}")

    assessment["persisted_records_count"] = len(persisted_records)
    assessment["application_number"] = app_row.get("application_number")
    assessment["application_status"] = app_row.get("status")

    # If user is applicant, sanitize details to prevent exposing internal system paths
    if user_role == "applicant":
        sanitized_reasons = []
        for r in assessment["reasons"]:
            sanitized_reasons.append({
                "type": r["type"],
                "field": r.get("field"),
                "severity": r.get("severity"),
                "document_type": r.get("document_type"),
                "message": r.get("message"),
            })
        return {
            "application_id": application_id,
            "status": assessment["status"],
            "risk_level": assessment["risk_level"],
            "anomaly_score": assessment["anomaly_score"],
            "recommended_action": assessment.get("recommended_action"),
            "summary": assessment["summary"],
            "reasons": sanitized_reasons,
            "detected_at": assessment["detected_at"],
            "is_advisory": True,
            "human_review_required": assessment.get("human_review_required", assessment["status"] == "ANOMALY_DETECTED"),
        }

    # Admin view includes full details and persisted records
    assessment["persisted_records"] = persisted_records
    return assessment
