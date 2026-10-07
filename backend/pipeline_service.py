"""
pipeline_service.py
-------------------

Orchestrates the complete scholarship application lifecycle:
1. Application validation & creation (SUBMITTED)
2. Transition to DOCUMENT_CHECK
3. Document storage in Supabase Storage & record creation in 'documents'
4. Text extraction, structured field extraction, and application/profile cross-checking
5. Application-level verification summary generation
6. Database-driven scholarship rules eligibility evaluation
7. ML prediction + SHAP explanation persistence (AI_PROCESSING)
8. Transition to HUMAN_REVIEW (AI NEVER auto-approves or rejects)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from backend.supabase_client import supabase
    from backend.application_service import (
        create_application,
        update_application_status,
        get_application_by_id,
        get_application_verification_data,
    )
    from backend.document_service import (
        create_document,
        upload_document_bytes,
        process_document,
    )
    from backend.verification_service import generate_verification_summary
    from backend.eligibility_service import evaluate_application_eligibility
    from backend.prediction_service import save_prediction
    from backend.anomaly_detection_service import (
        analyze_and_record_application_anomalies,
    )
except ImportError:
    from supabase_client import supabase
    from application_service import (
        create_application,
        update_application_status,
        get_application_by_id,
        get_application_verification_data,
    )
    from document_service import (
        create_document,
        upload_document_bytes,
        process_document,
    )
    from verification_service import generate_verification_summary
    from eligibility_service import evaluate_application_eligibility
    from prediction_service import save_prediction
    from anomaly_detection_service import (
        analyze_and_record_application_anomalies,
    )


logger = logging.getLogger(__name__)


# Canonical fallback mapping if dynamic lookup needs fallback
FALLBACK_SCHEME_IDS = {
    "MERIT": "91fc26f7-e746-4dae-862b-ddc1a8c3527c",
    "NEED_BASED": "cc4304cd-d84e-40f7-8085-dbd7c2d21f56",
    "CATEGORY": "42415966-00bc-455f-ad9a-30e884786b67",
}


def resolve_scholarship_scheme(scheme_identifier: str) -> Dict[str, Any]:
    """
    Resolve scholarship scheme record from Supabase dynamically by:
    - UUID id
    - scheme_code (e.g. MERIT, NEED_BASED, CATEGORY)
    - scheme_name (e.g. Merit Scholarship)
    """
    scheme_identifier = str(scheme_identifier).strip()

    if not scheme_identifier:
        raise ValueError("Scholarship scheme identifier is required.")

    # 1. Try querying by id if it looks like a UUID
    if len(scheme_identifier) == 36 and "-" in scheme_identifier:
        res = (
            supabase
            .table("scholarship_schemes")
            .select("id, scheme_code, scheme_name, description, required_documents, is_active")
            .eq("id", scheme_identifier)
            .execute()
        )
        if res.data:
            return res.data[0]

    # 2. Try querying by scheme_code (case-insensitive uppercase)
    code_query = scheme_identifier.upper().replace("-", "_").replace(" ", "_")
    res = (
        supabase
        .table("scholarship_schemes")
        .select("id, scheme_code, scheme_name, description, required_documents, is_active")
        .eq("scheme_code", code_query)
        .execute()
    )
    if res.data:
        return res.data[0]

    # 3. Try querying by scheme_name
    res = (
        supabase
        .table("scholarship_schemes")
        .select("id, scheme_code, scheme_name, description, required_documents, is_active")
        .ilike("scheme_name", f"%{scheme_identifier}%")
        .execute()
    )
    if res.data:
        return res.data[0]

    # 4. Fallback check using canonical scheme IDs
    fallback_id = FALLBACK_SCHEME_IDS.get(code_query)
    if fallback_id:
        res = (
            supabase
            .table("scholarship_schemes")
            .select("id, scheme_code, scheme_name, description, required_documents, is_active")
            .eq("id", fallback_id)
            .execute()
        )
        if res.data:
            return res.data[0]

    raise ValueError(
        f"Scholarship scheme '{scheme_identifier}' not found in active schemes."
    )


try:
    from backend.validation import (
        validate_academic_score,
        validate_attendance,
        validate_annual_income,
        validate_application_category,
        validate_full_name,
        validate_phone_number,
        validate_email,
    )
except ImportError:
    from validation import (
        validate_academic_score,
        validate_attendance,
        validate_annual_income,
        validate_application_category,
        validate_full_name,
        validate_phone_number,
        validate_email,
    )


def validate_application_form_fields(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate numeric, string guardrails, and categorical input fields for scholarship application.
    """
    required_fields = [
        "academic_score",
        "previous_score",
        "attendance",
        "annual_income",
        "application_category",
        "scholarship_scheme",
    ]

    missing = [f for f in required_fields if f not in form_data or form_data[f] is None or str(form_data[f]).strip() == ""]
    if missing:
        raise ValueError(f"Missing required form fields: {missing}")

    # Validate full_name if supplied in form_data
    if "full_name" in form_data and form_data["full_name"]:
        ok, _, err = validate_full_name(form_data["full_name"])
        if not ok:
            raise ValueError(err)

    # Validate phone if supplied in form_data
    if "phone" in form_data and form_data["phone"]:
        ok, _, err = validate_phone_number(form_data["phone"], required=False)
        if not ok:
            raise ValueError(err)

    # Validate email if supplied in form_data
    if "email" in form_data and form_data["email"]:
        ok, _, err = validate_email(form_data["email"])
        if not ok:
            raise ValueError(err)

    ok_acad, academic_score, err_acad = validate_academic_score(form_data["academic_score"])
    if not ok_acad:
        raise ValueError(err_acad)

    ok_prev, previous_score, err_prev = validate_academic_score(form_data["previous_score"])
    if not ok_prev:
        raise ValueError(f"previous_score: {err_prev}")

    ok_att, attendance, err_att = validate_attendance(form_data["attendance"])
    if not ok_att:
        raise ValueError(err_att)

    ok_inc, annual_income, err_inc = validate_annual_income(form_data["annual_income"])
    if not ok_inc:
        raise ValueError(err_inc)

    ok_cat, category, err_cat = validate_application_category(str(form_data["application_category"]))
    if not ok_cat:
        raise ValueError(err_cat)

    scheme_identifier = str(form_data["scholarship_scheme"]).strip()

    return {
        "academic_score": academic_score,
        "previous_score": previous_score,
        "attendance": attendance,
        "annual_income": annual_income,
        "application_category": category,
        "scholarship_scheme": scheme_identifier,
    }



def submit_and_process_application(
    applicant_id: str,
    form_data: Dict[str, Any],
    files: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Full backend processing pipeline:
    Step 1: Input validation & scheme resolution
    Step 2: Create application in Supabase (status: SUBMITTED)
    Step 3: Transition to DOCUMENT_CHECK
    Step 4: Upload documents to Supabase Storage & create 'documents' rows
    Step 5: Run document extraction, structured fields & cross-checking
    Step 6: Generate application-level verification summary
    Step 7: Evaluate eligibility rules from scholarship_rules
    Step 8: If verified, transition to AI_PROCESSING, generate ML prediction + SHAP,
            save to ai_predictions, then transition to HUMAN_REVIEW.
            If not verified, route directly to HUMAN_REVIEW.
            (AI NEVER auto-approves or rejects).
    """
    # -------------------------------------------------------------
    # Step 1: Input validation & dynamic scheme resolution
    # -------------------------------------------------------------
    validated_fields = validate_application_form_fields(form_data)
    scheme = resolve_scholarship_scheme(validated_fields["scholarship_scheme"])
    scholarship_scheme_id = scheme["id"]
    required_documents = scheme.get("required_documents") or []

    # -------------------------------------------------------------
    # Step 2: Create application record in Supabase (SUBMITTED)
    # -------------------------------------------------------------
    app_response = create_application(
        applicant_id=applicant_id,
        scholarship_scheme_id=scholarship_scheme_id,
        academic_score=validated_fields["academic_score"],
        previous_score=validated_fields["previous_score"],
        attendance=validated_fields["attendance"],
        annual_income=validated_fields["annual_income"],
        application_category=validated_fields["application_category"],
    )

    if not app_response.data:
        raise RuntimeError("Failed to create application record in Supabase.")

    application_record = app_response.data[0]
    application_id = application_record["id"]
    application_number = application_record.get("application_number", "")

    # -------------------------------------------------------------
    # Step 3: Transition to DOCUMENT_CHECK
    # -------------------------------------------------------------
    try:
        update_application_status(application_id, "DOCUMENT_CHECK")
    except Exception as e:
        logger.warning(f"Could not transition status to DOCUMENT_CHECK: {e}")

    # -------------------------------------------------------------
    # Step 4 & 5: Upload & process documents
    # -------------------------------------------------------------
    processed_documents = []
    document_errors = []

    doc_types_to_process = list(dict.fromkeys(
        list(required_documents) + [
            k for k in files if k in [
                "marksheet",
                "income_certificate",
                "id_proof",
                "category_certificate"
            ]
        ]
    ))

    for doc_type in doc_types_to_process:
        if doc_type not in files:
            continue

        file_item = files[doc_type]
        file_bytes: Optional[bytes] = None
        file_name: str = f"{doc_type}.pdf"

        # Handle file input whether tuple, FileStorage, or bytes
        if hasattr(file_item, "read"):
            file_bytes = file_item.read()
            if hasattr(file_item, "filename") and file_item.filename:
                file_name = file_item.filename
        elif isinstance(file_item, tuple) and len(file_item) >= 2:
            file_name = file_item[0] or f"{doc_type}.pdf"
            file_bytes = file_item[1]
        elif isinstance(file_item, bytes):
            file_bytes = file_item
        elif isinstance(file_item, str):
            # Might be local path in tests
            try:
                with open(file_item, "rb") as f:
                    file_bytes = f.read()
                file_name = Path(file_item).name
            except Exception as read_err:
                document_errors.append(f"Could not read file for {doc_type}: {read_err}")
                continue

        if not file_bytes:
            continue

        # Sanitize file_name to avoid path traversal
        clean_name = file_name.replace("/", "_").replace("\\", "_")

        try:
            # Upload to Supabase Storage
            storage_path = upload_document_bytes(
                application_id=application_id,
                document_type=doc_type,
                file_name=clean_name,
                file_bytes=file_bytes,
                content_type="application/pdf",
                upsert=True
            )

            # Create document record
            doc_record_res = create_document(
                application_id=application_id,
                document_type=doc_type,
                file_name=clean_name,
                storage_path=storage_path,
            )
            doc_id = doc_record_res.data[0]["id"]

            # Process extraction and cross-check
            process_res = process_document(
                document_id=doc_id,
                application_id=application_id,
                document_type=doc_type,
                storage_path=storage_path,
            )
            processed_documents.append({
                "document_id": doc_id,
                "document_type": doc_type,
                "file_name": clean_name,
                "storage_path": storage_path,
                "process_result": process_res.data if hasattr(process_res, "data") else process_res,
            })

        except Exception as doc_err:
            logger.error(f"Error processing document {doc_type} for application {application_id}: {doc_err}")
            document_errors.append(f"Failed to process {doc_type}: {str(doc_err)}")

    # -------------------------------------------------------------
    # Step 6: Application-level Verification Summary
    # -------------------------------------------------------------
    verification_summary = generate_verification_summary(application_id)
    overall_status = verification_summary.get("overall_status", "INCOMPLETE")

    # -------------------------------------------------------------
    # Step 7: Feature 3 - Document Anomaly Detection
    # -------------------------------------------------------------
    anomaly_assessment = None

    try:
        anomaly_assessment = analyze_and_record_application_anomalies(
            application_id=application_id,
            applicant_id=applicant_id,
            verification_summary=verification_summary,
            actor_id=applicant_id,
        )
    except Exception as anomaly_err:
        logger.error(
            f"Anomaly detection error for application "
            f"{application_id}: {anomaly_err}"
        )

        # Fail safely: anomaly detection failure must never result
        # in automatic approval.
        anomaly_assessment = {
            "application_id": application_id,
            "status": "NEEDS_HUMAN_REVIEW",
            "risk_level": "HIGH",
            "anomaly_score": 100.0,
            "recommended_action": "NEEDS_HUMAN_REVIEW",
            "summary": "Anomaly detection could not be completed due to system error.",
            "anomalies_count": 1,
            "reasons": [
                {
                    "type": "SYSTEM_ERROR",
                    "category": "SYSTEM_FAILURE",
                    "severity": "HIGH",
                    "score_weight": 100.0,
                    "score": 100.0,
                    "message": f"Anomaly detection system error: {str(anomaly_err)}",
                    "details": {"error": str(anomaly_err)},
                }
            ],
            "is_advisory": True,
            "human_review_required": True,
        }

    # -------------------------------------------------------------
    # Step 7: Evaluate Eligibility Rules
    # -------------------------------------------------------------
    eligibility_result = None
    try:
        eligibility_result = evaluate_application_eligibility(
            application_id=application_id,
            scholarship_scheme_id=scholarship_scheme_id,
        )
    except Exception as elig_err:
        logger.error(f"Error evaluating eligibility for application {application_id}: {elig_err}")
        eligibility_result = {
            "eligible": False,
            "error": str(elig_err),
            "passed_rules": [],
            "failed_rules": [{"rule_code": "SYSTEM_ERROR", "message": str(elig_err)}],
            "total_rules": 0,
            "passed_count": 0,
            "failed_count": 1,
        }

    # -------------------------------------------------------------
    # Step 8: AI Processing & Human Review Routing
    # -------------------------------------------------------------
    ai_prediction_data = None

    # Step 8: AI Processing & Human Review Routing
    # Run trained ML model to generate advisory prediction + confidence
    try:
        update_application_status(application_id, "AI_PROCESSING")
        prediction_records = save_prediction(application_id)
        if prediction_records:
            ai_prediction_data = prediction_records[0]
    except Exception as ml_err:
        logger.error(f"ML prediction error for application {application_id}: {ml_err}")
        ai_prediction_data = {"error": f"ML processing error: {str(ml_err)}"}

    # After ML prediction, transition strictly to HUMAN_REVIEW (AI NEVER auto-approves or rejects)
    update_application_status(application_id, "HUMAN_REVIEW")
    final_status = "HUMAN_REVIEW"


    # Fetch updated application record
    final_app = get_application_by_id(application_id, applicant_id)

    return {
        "message": "Application submitted and processed successfully.",
        "application_id": application_id,
        "application_number": application_number,
        "status": final_status,
        "application": final_app or application_record,
        "scholarship_scheme": {
            "id": scheme["id"],
            "scheme_code": scheme.get("scheme_code"),
            "scheme_name": scheme.get("scheme_name"),
            "required_documents": required_documents,
        },
        "processed_documents": processed_documents,
        "document_errors": document_errors,
        "verification_summary": verification_summary,
        "anomaly_assessment": anomaly_assessment,
        "eligibility_summary": eligibility_result,
        "ai_prediction": ai_prediction_data,
        "document_verification": {
            "overall_status": overall_status,
            "required_documents": required_documents,
            "per_document": verification_summary.get("documents", {}),
        },
    }



