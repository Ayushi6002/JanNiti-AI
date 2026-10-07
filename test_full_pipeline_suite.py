"""
test_full_pipeline_suite.py
----------------------------
Comprehensive integration test suite covering all 7 required scenarios
from the Jan Niti AI specification:

TEST 1 — Complete valid application
TEST 2 — Missing document
TEST 3 — Mismatched document
TEST 4 — Eligibility failure
TEST 5 — ML prediction persistence
TEST 6 — Human decision workflow
TEST 7 — Student appeal workflow
"""

import sys
import io
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase


def log_test(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_all_tests():
    client = app.test_client()

    log_test("STEP 0: Authenticating Test Users")
    applicant_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
    applicant_token = applicant_auth.session.access_token
    applicant_headers = {"Authorization": f"Bearer {applicant_token}"}
    applicant_id = applicant_auth.user.id
    print(f"Applicant authenticated. ID: {applicant_id}")

    admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    admin_token = admin_auth.session.access_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = admin_auth.user.id
    print(f"Admin authenticated. ID: {admin_id}")

    # Load test PDF files
    with open("test_marksheet.pdf", "rb") as f:
        marksheet_pdf = f.read()
    with open("test_id_proof.pdf", "rb") as f:
        id_proof_pdf = f.read()
    with open("test_income_certificate.pdf", "rb") as f:
        income_pdf = f.read()
    with open("test_category_certificate.pdf", "rb") as f:
        category_pdf = f.read()
    with open("test_marksheet_mismatch.pdf", "rb") as f:
        mismatch_marksheet_pdf = f.read()

    # ==============================================================
    # TEST 1 — Complete valid application
    # ==============================================================
    log_test("TEST 1 — Complete Valid Application")
    t1_form = {
        "academic_score": "88.5",
        "previous_score": "84.0",
        "attendance": "92.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }

    res1 = client.post(
        "/submit-application-full",
        data=t1_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )

    print(f"Status Code: {res1.status_code}")
    data1 = res1.get_json()
    assert res1.status_code == 201, f"Test 1 failed: {data1}"

    app_id_1 = data1["application_id"]
    print(f"Application Created: {app_id_1}, App Number: {data1.get('application_number')}")
    print(f"Application Status: {data1.get('status')}")
    print(f"Verification Overall Status: {data1['verification_summary'].get('overall_status')}")
    print(f"Eligibility Eligible: {data1['eligibility_summary'].get('eligible')}")
    print(f"AI Prediction: {data1.get('ai_prediction', {}).get('prediction') if data1.get('ai_prediction') else None}")

    # Assertions for TEST 1
    assert data1["status"] == "HUMAN_REVIEW", f"Status must be HUMAN_REVIEW, got: {data1.get('status')}"
    assert data1["status"] != "APPROVED", "AI must NEVER directly approve!"
    assert data1["verification_summary"]["overall_status"] == "VERIFIED", "Document verification should be VERIFIED"
    assert len(data1["verification_summary"]["missing_documents"]) == 0, "No documents should be missing"
    assert len(data1["verification_summary"]["mismatched_documents"]) == 0, "No documents should be mismatched"
    assert data1["eligibility_summary"]["eligible"] is True, "Application should be eligible under rules"
    assert data1["ai_prediction"] is not None, "AI prediction must be generated and persisted"
    print(">>> TEST 1 PASSED: Complete valid application reached HUMAN_REVIEW with VERIFIED docs and eligibility PASS.")

    # ==============================================================
    # TEST 2 — Missing document
    # ==============================================================
    log_test("TEST 2 — Missing Document Application")
    t2_form = {
        "academic_score": "88.5",
        "previous_score": "84.0",
        "attendance": "92.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        # income_certificate deliberately omitted
    }

    res2 = client.post(
        "/submit-application-full",
        data=t2_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )

    print(f"Status Code: {res2.status_code}")
    data2 = res2.get_json()
    assert res2.status_code == 201, f"Test 2 failed: {data2}"

    app_id_2 = data2["application_id"]
    print(f"Application Created: {app_id_2}")
    print(f"Application Status: {data2.get('status')}")
    print(f"Verification Overall Status: {data2['verification_summary'].get('overall_status')}")
    print(f"Missing Documents: {data2['verification_summary'].get('missing_documents')}")

    # Assertions for TEST 2
    assert data2["status"] == "HUMAN_REVIEW", f"Status must be HUMAN_REVIEW, got: {data2.get('status')}"
    assert data2["status"] != "APPROVED", "Must not auto-approve"
    assert data2["verification_summary"]["overall_status"] == "INCOMPLETE", "Verification status must be INCOMPLETE"
    assert "income_certificate" in data2["verification_summary"]["missing_documents"], "income_certificate must be flagged missing"
    print(">>> TEST 2 PASSED: Missing document correctly detected as INCOMPLETE, routed safely to HUMAN_REVIEW.")

    # ==============================================================
    # TEST 3 — Mismatched document
    # ==============================================================
    log_test("TEST 3 — Mismatched Document Application")
    t3_form = {
        "academic_score": "88.5", # Form claims 88.5
        "previous_score": "84.0",
        "attendance": "92.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(mismatch_marksheet_pdf), "test_marksheet_mismatch.pdf"), # PDF has 72.0!
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }

    res3 = client.post(
        "/submit-application-full",
        data=t3_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )

    print(f"Status Code: {res3.status_code}")
    data3 = res3.get_json()
    assert res3.status_code == 201, f"Test 3 failed: {data3}"

    app_id_3 = data3["application_id"]
    print(f"Application Created: {app_id_3}")
    print(f"Application Status: {data3.get('status')}")
    print(f"Verification Overall Status: {data3['verification_summary'].get('overall_status')}")
    print(f"Mismatched Documents: {data3['verification_summary'].get('mismatched_documents')}")

    # Assertions for TEST 3
    assert data3["status"] == "HUMAN_REVIEW", f"Status must be HUMAN_REVIEW, got: {data3.get('status')}"
    assert data3["status"] != "APPROVED", "Must not auto-approve mismatched document"
    assert data3["verification_summary"]["overall_status"] == "NEEDS_REVIEW", "Verification status must be NEEDS_REVIEW"
    assert "marksheet" in data3["verification_summary"]["mismatched_documents"], "marksheet must be flagged as mismatched"
    print(">>> TEST 3 PASSED: Cross-check detected score mismatch, routed safely to HUMAN_REVIEW.")

    # ==============================================================
    # TEST 4 — Eligibility failure
    # ==============================================================
    log_test("TEST 4 — Eligibility Failure Application")
    t4_form = {
        "academic_score": "45.0", # Below MERIT min score of 75.0!
        "previous_score": "50.0", # Below MERIT min score of 70.0!
        "attendance": "60.0",     # Below MERIT min attendance of 75.0!
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }

    res4 = client.post(
        "/submit-application-full",
        data=t4_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )

    print(f"Status Code: {res4.status_code}")
    data4 = res4.get_json()
    assert res4.status_code == 201, f"Test 4 failed: {data4}"

    app_id_4 = data4["application_id"]
    print(f"Application Created: {app_id_4}")
    print(f"Eligibility Eligible: {data4['eligibility_summary'].get('eligible')}")
    print(f"Failed Rules Count: {data4['eligibility_summary'].get('failed_count')}")
    print(f"Failed Rules: {[r['rule_code'] for r in data4['eligibility_summary'].get('failed_rules', [])]}")

    # Assertions for TEST 4
    assert data4["eligibility_summary"]["eligible"] is False, "Application should NOT be eligible"
    assert data4["eligibility_summary"]["failed_count"] > 0, "Failed rules count should be > 0"
    assert data4["status"] != "APPROVED", "Failed eligibility must not be approved"
    print(">>> TEST 4 PASSED: Eligibility engine correctly evaluated rules from database and flagged failure.")

    # ==============================================================
    # TEST 5 — ML prediction persistence
    # ==============================================================
    log_test("TEST 5 — ML Prediction Persistence Verification")
    pred_query = (
        supabase
        .table("ai_predictions")
        .select("*")
        .eq("application_id", app_id_1)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    assert pred_query.data, f"No AI prediction found in ai_predictions for app_id {app_id_1}"
    db_pred = pred_query.data[0]
    print(f"Prediction Record ID: {db_pred['id']}")
    print(f"Model Version: {db_pred['model_version']}")
    print(f"Prediction: {db_pred['prediction']}")
    print(f"Probability: {db_pred['probability']}")
    print(f"Top Reasons: {len(db_pred['top_reasons'])} reasons generated")
    print(f"Feature Breakdown: {bool(db_pred['feature_breakdown'])}")

    assert db_pred["application_id"] == app_id_1
    assert db_pred["model_version"] == "jan_niti_rf_v2"
    assert db_pred["prediction"] in {"APPROVE", "REJECT", "NEEDS_HUMAN_REVIEW"}
    assert isinstance(db_pred["probability"], (float, int))
    assert isinstance(db_pred["top_reasons"], list) and len(db_pred["top_reasons"]) > 0
    assert db_pred["explanation"] is not None
    print(">>> TEST 5 PASSED: ai_predictions table properly persists model output, SHAP reasons, and metadata.")

    # ==============================================================
    # TEST 6 — Human decision workflow
    # ==============================================================
    log_test("TEST 6 — Human Decision Workflow (Admin)")
    # Approve Test 1
    approve_body = {
        "application_id": app_id_1,
        "decision": "APPROVED",
        "reason": "Exemplary academic credentials and verified documents",
        "ai_prediction_id": db_pred["id"],
        "admin_comment": "Scholarship awarded with high commendation.",
    }

    res6_app = client.post(
        "/admin/decision",
        data=json.dumps(approve_body),
        content_type="application/json",
        headers=admin_headers,
    )

    print(f"Approve Status Code: {res6_app.status_code}")
    data6_app = res6_app.get_json()
    assert res6_app.status_code == 200, f"Approval failed: {data6_app}"

    # Verify status in applications table
    app1_check = supabase.table("applications").select("status").eq("id", app_id_1).single().execute()
    assert app1_check.data["status"] == "APPROVED", f"Expected APPROVED, got {app1_check.data['status']}"

    # Reject Test 4 (which failed eligibility)
    reject_body = {
        "application_id": app_id_4,
        "decision": "REJECTED",
        "reason": "Does not satisfy minimum academic score requirement for Merit Scholarship",
        "admin_comment": "Advised to apply for Academic Support after improving scores.",
    }

    res6_rej = client.post(
        "/admin/decision",
        data=json.dumps(reject_body),
        content_type="application/json",
        headers=admin_headers,
    )
    print(f"Reject Status Code: {res6_rej.status_code}")
    assert res6_rej.status_code == 200, f"Rejection failed: {res6_rej.get_json()}"

    app4_check = supabase.table("applications").select("status").eq("id", app_id_4).single().execute()
    assert app4_check.data["status"] == "REJECTED", f"Expected REJECTED, got {app4_check.data['status']}"

    # Verify audit logs created
    audit_check = (
        supabase
        .table("audit_logs")
        .select("*")
        .eq("application_id", app_id_1)
        .order("created_at", desc=True)
        .execute()
    )
    assert audit_check.data, "Audit log must be created on human decision"
    print(f"Audit log verified: Action '{audit_check.data[0]['action']}' by user {audit_check.data[0].get('actor_id')}")

    # Verify protection against re-deciding finalized application
    res6_block = client.post(
        "/admin/decision",
        data=json.dumps(approve_body),
        content_type="application/json",
        headers=admin_headers,
    )
    assert res6_block.status_code == 400, "Should block modifying an already finalized application"
    print(f"Finalized protection verified: {res6_block.get_json().get('error')}")
    print(">>> TEST 6 PASSED: Human decision recorded, status updated, audit logged, and protection verified.")

    # ==============================================================
    # TEST 7 — Appeal workflow
    # ==============================================================
    log_test("TEST 7 — Appeal Workflow")
    # Student submits appeal on the REJECTED application (app_id_4)
    appeal_payload = {
        "application_id": app_id_4,
        "reason": "I had documented medical leave during the semester examinations, medical certificate attached."
    }

    res7_submit = client.post(
        "/student/appeals",
        data=json.dumps(appeal_payload),
        content_type="application/json",
        headers=applicant_headers,
    )
    print(f"Submit Appeal Code: {res7_submit.status_code}")
    data7_submit = res7_submit.get_json()
    assert res7_submit.status_code == 201, f"Appeal submission failed: {data7_submit}"
    appeal_record = data7_submit["appeal"]
    appeal_id = appeal_record["id"]
    print(f"Appeal Created: {appeal_id}, Status: {appeal_record['status']}")
    assert appeal_record["status"] == "PENDING"

    # Verify application transitioned to APPEAL_PENDING
    app4_appeal_status = supabase.table("applications").select("status").eq("id", app_id_4).single().execute()
    assert app4_appeal_status.data["status"] == "APPEAL_PENDING", f"Expected APPEAL_PENDING, got {app4_appeal_status.data['status']}"

    # Student views appeals
    res7_student_list = client.get("/student/appeals", headers=applicant_headers)
    assert res7_student_list.status_code == 200
    student_appeals = res7_student_list.get_json()["appeals"]
    assert any(a["id"] == appeal_id for a in student_appeals), "Created appeal must appear in student list"
    print(f"Student appeals count: {len(student_appeals)}")

    # Admin views appeals
    res7_admin_list = client.get("/admin/appeals", headers=admin_headers)
    assert res7_admin_list.status_code == 200
    admin_appeals = res7_admin_list.get_json()["appeals"]
    assert any(a["id"] == appeal_id for a in admin_appeals), "Created appeal must appear in admin list"
    print(f"Admin appeals count: {len(admin_appeals)}")

    # Admin reviews appeal (RESOLVED)
    review_payload = {
        "status": "RESOLVED",
        "review_comment": "Medical documentation accepted. Granted second evaluation chance."
    }
    res7_review = client.post(
        f"/admin/appeals/{appeal_id}/review",
        data=json.dumps(review_payload),
        content_type="application/json",
        headers=admin_headers,
    )
    print(f"Review Appeal Code: {res7_review.status_code}")
    data7_review = res7_review.get_json()
    assert res7_review.status_code == 200, f"Review failed: {data7_review}"
    assert data7_review["appeal"]["status"] == "RESOLVED"
    print(f"Appeal successfully reviewed: Status={data7_review['appeal']['status']}, Comment={data7_review['appeal']['review_comment']}")

    print(">>> TEST 7 PASSED: Full student appeal and admin review lifecycle completed successfully.")

    # ==============================================================
    # ADDITIONAL VERIFICATION: Query endpoints
    # ==============================================================
    log_test("EXTRA CHECKS — Enriched Query Endpoints")
    # /status/<app_id>
    st_res = client.get(f"/status/{app_id_1}", headers=applicant_headers)
    assert st_res.status_code == 200
    st_data = st_res.get_json()
    assert st_data["status"] == "APPROVED"
    assert st_data["decision"] is not None
    assert st_data["verification_summary"] is not None
    print(f"GET /status/{app_id_1}: OK (status={st_data['status']}, decision={st_data['decision']['decision']})")

    # /admin/applications/<app_id>
    adm_res = client.get(f"/admin/applications/{app_id_1}", headers=admin_headers)
    assert adm_res.status_code == 200
    adm_data = adm_res.get_json()
    assert adm_data["application"]["id"] == app_id_1
    assert adm_data["documents"] is not None
    assert adm_data["ai_prediction"] is not None
    assert adm_data["decisions"] is not None
    print(f"GET /admin/applications/{app_id_1}: OK (applicant={adm_data.get('applicant', {}).get('full_name')})")

    # /student/applications/<app_id>/verification
    ver_res = client.get(f"/student/applications/{app_id_1}/verification", headers=applicant_headers)
    assert ver_res.status_code == 200
    print(f"GET /student/applications/{app_id_1}/verification: OK (overall={ver_res.get_json().get('overall_status')})")

    # /student/applications/<app_id>/decision
    dec_res = client.get(f"/student/applications/{app_id_1}/decision", headers=applicant_headers)
    assert dec_res.status_code == 200
    print(f"GET /student/applications/{app_id_1}/decision: OK (decision={dec_res.get_json().get('decision', {}).get('decision')})")

    log_test("ALL 7 INTEGRATION TESTS & EXTRA ENDPOINT CHECKS PASSED!")


if __name__ == "__main__":
    run_all_tests()
