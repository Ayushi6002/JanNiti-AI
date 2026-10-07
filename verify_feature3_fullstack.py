"""
verify_feature3_fullstack.py
-----------------------------
Verification test script for Full-Stack Feature 3: Document Fraud & Anomaly Detection.

Validates:
1. Student Anomaly API (GET /student/applications/<app_id>/anomalies): sanitized view, 200 OK.
2. Admin Anomaly API (GET /admin/applications/<app_id>/anomalies): full details, persisted records, 200 OK.
3. Strict Authorization Enforcement: 403 Forbidden for cross-student access, 401 for unauthenticated.
4. Production Persistence in Supabase: Assessment is persisted to Supabase audit_logs and recoverable.
5. Fail-Safe Pipeline Integration: Pipeline outputs anomaly_assessment and routes to HUMAN_REVIEW.
6. Frontend File Integrity: All frontend files and styles are correctly wired to real APIs.
"""

import io
import json
import sys
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase
from backend import db
from backend.anomaly_detection_service import (
    get_application_anomalies,
    record_anomaly_assessment,
    analyze_application_anomalies,
    ForbiddenAnomalyAccessError,
    ApplicationNotFoundError,
)


def log(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def run_fullstack_verification():
    client = app.test_client()

    log("STEP 1: Authenticating Test Users (Supabase Auth)")
    # 1. Student / Applicant Auth
    applicant_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
    applicant_token = applicant_auth.session.access_token
    applicant_headers = {"Authorization": f"Bearer {applicant_token}"}
    applicant_id = applicant_auth.user.id
    print(f"Student authenticated. ID: {applicant_id}")

    # 2. Admin Auth
    admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    admin_token = admin_auth.session.access_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = admin_auth.user.id
    print(f"Admin authenticated. ID: {admin_id}")

    # Load test PDFs
    with open("test_marksheet.pdf", "rb") as f:
        marksheet_pdf = f.read()
    with open("test_id_proof.pdf", "rb") as f:
        id_proof_pdf = f.read()
    with open("test_income_certificate.pdf", "rb") as f:
        income_pdf = f.read()
    with open("test_marksheet_mismatch.pdf", "rb") as f:
        mismatch_marksheet_pdf = f.read()

    # -------------------------------------------------------------
    # STEP 2: Submit Application with Document Anomaly via Pipeline
    # -------------------------------------------------------------
    log("STEP 2: Submitting Application with Mismatched Marksheet")
    form_data = {
        "academic_score": "95.0",  # Application form says 95.0, document has 72.0
        "previous_score": "84.0",
        "attendance": "90.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(mismatch_marksheet_pdf), "test_marksheet_mismatch.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }
    submit_res = client.post(
        "/submit-application-full",
        data=form_data,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert submit_res.status_code == 201, f"Submission failed: {submit_res.get_json()}"
    app_result = submit_res.get_json()
    app_id = app_result["application_id"]
    print(f"Application created: {app_id}")
    print(f"Pipeline status: {app_result['status']}")

    assert "anomaly_assessment" in app_result, "Response must include anomaly_assessment"
    pipeline_assessment = app_result["anomaly_assessment"]
    assert pipeline_assessment["status"] == "ANOMALY_DETECTED"
    assert pipeline_assessment["risk_level"] in ("MEDIUM", "HIGH")
    assert pipeline_assessment["anomaly_score"] > 0
    assert pipeline_assessment["human_review_required"] is True
    print(f"Pipeline assessment verified: Score={pipeline_assessment['anomaly_score']}, Risk={pipeline_assessment['risk_level']}")
    print(">>> STEP 2 PASSED: Pipeline executes Feature 3 anomaly detection and routes to HUMAN_REVIEW.")

    # -------------------------------------------------------------
    # STEP 3: Student View API Verification
    # -------------------------------------------------------------
    log("STEP 3: Student View API (GET /student/applications/<app_id>/anomalies)")
    student_res = client.get(
        f"/student/applications/{app_id}/anomalies",
        headers=applicant_headers,
    )
    assert student_res.status_code == 200, f"Expected 200, got {student_res.status_code}"
    student_data = student_res.get_json()

    # Validate student view requirements:
    assert student_data["status"] == "ANOMALY_DETECTED"
    assert student_data["risk_level"] in ("MEDIUM", "HIGH")
    assert student_data["anomaly_score"] > 0
    assert "summary" in student_data
    assert "reasons" in student_data
    assert len(student_data["reasons"]) > 0
    assert student_data["human_review_required"] is True
    assert student_data["is_advisory"] is True

    # Security check: verify sanitized (no internal paths, details, or persisted_records)
    assert "persisted_records" not in student_data, "Applicant view must not leak internal persisted_records"
    for r in student_data["reasons"]:
        assert "type" in r
        assert "message" in r
        assert "details" not in r, f"Applicant reason should not expose internal system details: {r}"
    print(f"Student sanitized response verified: {len(student_data['reasons'])} student-friendly reason(s).")
    print(">>> STEP 3 PASSED: Student receives sanitized anomaly report.")

    # -------------------------------------------------------------
    # STEP 4: Admin View API Verification
    # -------------------------------------------------------------
    log("STEP 4: Admin View API (GET /admin/applications/<app_id>/anomalies)")
    admin_res = client.get(
        f"/admin/applications/{app_id}/anomalies",
        headers=admin_headers,
    )
    assert admin_res.status_code == 200, f"Expected 200, got {admin_res.status_code}"
    admin_data = admin_res.get_json()

    # Validate admin view requirements:
    assert admin_data["anomaly_score"] > 0
    assert admin_data["risk_level"] in ("MEDIUM", "HIGH")
    assert admin_data["status"] == "ANOMALY_DETECTED"
    assert admin_data["recommended_action"] == "NEEDS_HUMAN_REVIEW"
    assert admin_data["human_review_required"] is True
    assert "reasons" in admin_data
    assert len(admin_data["reasons"]) > 0
    assert "persisted_records" in admin_data
    assert "persisted_records_count" in admin_data

    # Check reason detail includes document and type
    reason0 = admin_data["reasons"][0]
    assert "type" in reason0
    assert "category" in reason0
    assert "document_type" in reason0
    print(f"Admin view verified: {admin_data['anomalies_count']} anomalies detected, "
          f"{admin_data['persisted_records_count']} persisted records.")
    print(">>> STEP 4 PASSED: Admin receives full anomaly breakdown and persisted audit records.")

    # -------------------------------------------------------------
    # STEP 5: Authorization Security (403 and 401)
    # -------------------------------------------------------------
    log("STEP 5: Role-Based Authorization Enforcement")
    # 1. Create another application owned by admin
    admin_app = (
        supabase
        .table("applications")
        .insert({
            "applicant_id": admin_id,
            "scholarship_scheme_id": "91fc26f7-e746-4dae-862b-ddc1a8c3527c",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 90.0,
            "annual_income": 200000.0,
            "application_category": "GENERAL",
            "status": "SUBMITTED",
        })
        .execute()
    ).data[0]
    admin_app_id = admin_app["id"]

    # Student attempts to access admin_app anomalies -> 403 Forbidden
    cross_access_res = client.get(
        f"/student/applications/{admin_app_id}/anomalies",
        headers=applicant_headers,
    )
    print(f"Cross-student access attempt: {cross_access_res.status_code}")
    assert cross_access_res.status_code == 403, f"Expected 403, got {cross_access_res.status_code}"

    # Unauthenticated access -> 401 Unauthorized
    unauth_res = client.get(f"/student/applications/{app_id}/anomalies")
    assert unauth_res.status_code == 401, f"Expected 401, got {unauth_res.status_code}"
    print("Unauthenticated access attempt: 401")
    print(">>> STEP 5 PASSED: Strict authorization enforced (403 Forbidden for cross-access, 401 for unauth).")

    # -------------------------------------------------------------
    # STEP 6: Persistence in Supabase Audit Logs
    # -------------------------------------------------------------
    log("STEP 6: Verifying Production Persistence in Supabase")
    audit_res = (
        supabase
        .table("audit_logs")
        .select("*")
        .eq("application_id", app_id)
        .eq("entity_type", "document_anomalies")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    assert len(audit_res.data) > 0, "Expected anomaly assessment in Supabase audit_logs"
    persisted_audit = audit_res.data[0]
    new_val = persisted_audit.get("new_value") or {}
    print(f"Supabase Audit Log ID: {persisted_audit['id']}")
    print(f"Persisted action: {persisted_audit['action']}")
    print(f"Persisted status: {new_val.get('status')}")
    print(f"Persisted risk level: {new_val.get('risk_level')}")
    print(f"Persisted score: {new_val.get('anomaly_score')}")
    assert new_val.get("status") == "ANOMALY_DETECTED"
    assert new_val.get("anomaly_score") == pipeline_assessment["anomaly_score"]
    print(">>> STEP 6 PASSED: Anomaly assessment persisted in primary Supabase production database.")

    # -------------------------------------------------------------
    # STEP 7: Frontend Source Code & Wiring Verification
    # -------------------------------------------------------------
    log("STEP 7: Frontend Files and Wiring Verification")
    root = Path(__file__).resolve().parent

    track_js = (root / "frontend" / "js" / "track.js").read_text(encoding="utf-8")
    assert "/student/applications/" in track_js, "track.js must call /student/applications/<app_id>/anomalies"
    assert "anomaly-panel" in track_js, "track.js must render anomaly-panel"
    assert "risk-meter" in track_js, "track.js must render risk-meter"
    print("track.js: Verified calls to /student/applications/<app_id>/anomalies and renders UI.")

    admin_js = (root / "frontend" / "js" / "admin.js").read_text(encoding="utf-8")
    assert "/admin/applications/" in admin_js, "admin.js must call admin APIs"
    assert "anomalies" in admin_js, "admin.js must call /admin/applications/<app_id>/anomalies"
    assert "HUMAN REVIEW REQUIREMENT" in admin_js, "admin.js must display human review requirement"
    print("admin.js: Verified calls to /admin/applications/<app_id>/anomalies and renders detailed evaluator UI.")

    apply_js = (root / "frontend" / "js" / "apply.js").read_text(encoding="utf-8")
    assert "anomaly_assessment" in apply_js, "apply.js must render anomaly_assessment"
    print("apply.js: Verified rendering of anomaly assessment on decision certificate.")

    dashboard_html = (root / "frontend" / "user-dashboard.html").read_text(encoding="utf-8")
    assert "Document Risk" in dashboard_html, "user-dashboard.html must include Document Risk column"
    print("user-dashboard.html: Verified Document Risk column and track links.")

    style_css = (root / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    for cls in [".pill-risk-low", ".pill-risk-high", ".risk-meter", ".anomaly-card-item"]:
        assert cls in style_css, f"style.css must define {cls}"
    print("style.css: Verified Feature 3 styles and classes.")

    print("\n" + "=" * 65)
    print("  ALL FEATURE 3 FULL-STACK VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_fullstack_verification()
