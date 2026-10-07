"""
test_decision_passport.py
-------------------------
Focused test suite for FEATURE 1: AI DECISION PASSPORT.

Tests:
1. Nonexistent application -> 404
2. Applicant cannot retrieve another applicant's passport -> 403
3. Admin can retrieve an authorized application passport -> 200
4. Valid applicant can retrieve own passport -> 200
5. Application with AI prediction but NO human decision ->
   ai_recommendation populated, human_decision is null, final_decision is null
6. Application with AI prediction AND human decision ->
   AI recommendation clearly distinguished from Human decision
7. Application with missing documents ->
   documents.overall_status INCOMPLETE, missing_documents flagged
8. Application with mismatched documents ->
   documents.overall_status NEEDS_REVIEW, mismatch_details exposed
9. Application with eligibility failure ->
   eligibility.eligible is False, failed_rules & failed_reasons exposed
10. Application with appeal ->
   appeal.has_appeal is True, status and details exposed cleanly
"""

import io
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase


def log_test(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_decision_passport_tests():
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
    # TEST 1: Nonexistent application -> 404
    # -------------------------------------------------------------
    log_test("TEST 1: Nonexistent Application -> 404")
    res_404 = client.get(
        "/student/applications/00000000-0000-0000-0000-000000000000/decision-passport",
        headers=applicant_headers,
    )
    print(f"Response status: {res_404.status_code}")
    assert res_404.status_code == 404, f"Expected 404, got {res_404.status_code}"
    assert "error" in res_404.get_json()
    print(">>> TEST 1 PASSED: Nonexistent application correctly returned 404.")

    # -------------------------------------------------------------
    # TEST 2: Applicant cannot retrieve another applicant's passport -> 403
    # -------------------------------------------------------------
    log_test("TEST 2: Applicant Forbidden Access to Another's Passport -> 403")
    # Create an application that belongs to a different user (e.g. admin_id)
    other_app_res = (
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
    )
    other_app_id = other_app_res.data[0]["id"]
    print(f"Created application {other_app_id} belonging to user {admin_id}")

    res_403 = client.get(
        f"/student/applications/{other_app_id}/decision-passport",
        headers=applicant_headers,
    )
    print(f"Response status: {res_403.status_code}")
    assert res_403.status_code == 403, f"Expected 403, got {res_403.status_code}"
    assert "error" in res_403.get_json()
    print(">>> TEST 2 PASSED: Applicant blocked with 403 when requesting another's application.")

    # -------------------------------------------------------------
    # TEST 3: Admin can retrieve an authorized application passport -> 200
    # -------------------------------------------------------------
    log_test("TEST 3: Admin Access to Decision Passport -> 200")
    res_admin_student_route = client.get(
        f"/student/applications/{other_app_id}/decision-passport",
        headers=admin_headers,
    )
    assert res_admin_student_route.status_code == 200, (
        f"Admin accessing student passport endpoint failed: {res_admin_student_route.status_code}"
    )

    res_admin_admin_route = client.get(
        f"/admin/applications/{other_app_id}/decision-passport",
        headers=admin_headers,
    )
    assert res_admin_admin_route.status_code == 200, (
        f"Admin accessing admin passport endpoint failed: {res_admin_admin_route.status_code}"
    )
    print(">>> TEST 3 PASSED: Admin successfully accessed passport on both endpoints.")

    # -------------------------------------------------------------
    # Create a fresh complete application for the applicant
    # -------------------------------------------------------------
    log_test("SUBMITTING FRESH VALID APPLICATION FOR PASSPORT LIFECYCLE TESTS")
    form_valid = {
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
    submit_res = client.post(
        "/submit-application-full",
        data=form_valid,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert submit_res.status_code == 201, f"Submission failed: {submit_res.get_json()}"
    fresh_app_id = submit_res.get_json()["application_id"]
    print(f"Fresh application created: {fresh_app_id}")

    # -------------------------------------------------------------
    # TEST 4: Valid applicant can retrieve own passport -> 200
    # -------------------------------------------------------------
    log_test("TEST 4: Valid Applicant Retrieves Own Passport -> 200")
    res_own = client.get(
        f"/student/applications/{fresh_app_id}/decision-passport",
        headers=applicant_headers,
    )
    assert res_own.status_code == 200, f"Expected 200, got {res_own.status_code}"
    passport_data = res_own.get_json()
    assert "application" in passport_data
    assert "eligibility" in passport_data
    assert "documents" in passport_data
    assert "ai_recommendation" in passport_data
    assert "human_decision" in passport_data
    assert "audit" in passport_data
    assert "appeal" in passport_data
    print(">>> TEST 4 PASSED: Valid applicant successfully retrieved complete passport schema.")

    # -------------------------------------------------------------
    # TEST 5: Application with AI prediction but NO human decision
    # -------------------------------------------------------------
    log_test("TEST 5: AI Prediction Present, Human Decision Null (HUMAN_REVIEW)")
    assert passport_data["application"]["status"] == "HUMAN_REVIEW"
    assert passport_data["application"]["final_decision"] is None, "final_decision must be null before human review"
    assert passport_data["human_decision"] is None, "human_decision must be null before human review"

    ai_rec = passport_data["ai_recommendation"]
    assert ai_rec is not None, "AI recommendation must be present"
    assert ai_rec["prediction"] in {"APPROVE", "REJECT", "NEEDS_HUMAN_REVIEW"}
    assert isinstance(ai_rec["probability"], (float, int))
    assert ai_rec["model_version"] == "jan_niti_rf_v2"
    assert len(ai_rec["top_reasons"]) > 0
    assert len(ai_rec["readable_reasons"]) > 0
    assert "disclaimer" in ai_rec
    print(f"AI Recommendation Prediction: {ai_rec['prediction']}, Probability: {ai_rec['probability']}")
    print(f"Top readable reason: {ai_rec['readable_reasons'][0]}")
    print(f"Human decision status: {passport_data['human_decision']}")
    print(">>> TEST 5 PASSED: AI recommendation present while human decision correctly returned as null.")

    # -------------------------------------------------------------
    # TEST 6: Application with AI prediction AND human decision
    # -------------------------------------------------------------
    log_test("TEST 6: AI Recommendation vs Final Human Decision Distinction")
    ai_pred_record = (
        supabase
        .table("ai_predictions")
        .select("id")
        .eq("application_id", fresh_app_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    pred_id = ai_pred_record.data[0]["id"]

    # Admin makes human decision
    dec_body = {
        "application_id": fresh_app_id,
        "decision": "APPROVED",
        "reason": "Outstanding academic record and verified credentials.",
        "ai_prediction_id": pred_id,
        "admin_comment": "Awarded full scholarship.",
    }
    dec_res = client.post(
        "/admin/decision",
        data=json.dumps(dec_body),
        content_type="application/json",
        headers=admin_headers,
    )
    assert dec_res.status_code == 200, f"Decision recording failed: {dec_res.get_json()}"

    # Fetch passport again
    res_decided = client.get(
        f"/student/applications/{fresh_app_id}/decision-passport",
        headers=applicant_headers,
    )
    assert res_decided.status_code == 200
    p_decided = res_decided.get_json()

    # Verify AI recommendation remains an advisory recommendation
    assert p_decided["ai_recommendation"] is not None
    assert p_decided["ai_recommendation"]["prediction"] == "APPROVE"

    # Verify final human decision is recorded separately
    assert p_decided["human_decision"] is not None
    assert p_decided["human_decision"]["has_decision"] is True
    assert p_decided["human_decision"]["decision"] == "APPROVED"
    assert p_decided["human_decision"]["decision_type"] == "HUMAN"
    assert p_decided["human_decision"]["reason"] == "Outstanding academic record and verified credentials."
    assert p_decided["human_decision"]["decided_by"] == admin_id
    assert p_decided["application"]["final_decision"] == "APPROVED"
    assert p_decided["application"]["status"] == "APPROVED"

    # Verify audit event captured
    assert len(p_decided["audit"]["status_changes"]) > 0
    assert p_decided["audit"]["status_changes"][0]["new_status"] == "APPROVED"
    print(f"AI Recommendation: {p_decided['ai_recommendation']['prediction']} ({p_decided['ai_recommendation']['probability']})")
    print(f"Final Human Decision: {p_decided['human_decision']['decision']} by {p_decided['human_decision']['decided_by']}")
    print(">>> TEST 6 PASSED: AI recommendation clearly separated from Final human decision.")

    # -------------------------------------------------------------
    # TEST 7: Application with missing documents
    # -------------------------------------------------------------
    log_test("TEST 7: Application with Missing Documents")
    form_missing = {
        "academic_score": "88.0",
        "previous_score": "84.0",
        "attendance": "90.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        # id_proof and income_certificate missing
    }
    res_m_sub = client.post(
        "/submit-application-full",
        data=form_missing,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res_m_sub.status_code == 201
    missing_app_id = res_m_sub.get_json()["application_id"]

    p_missing = client.get(
        f"/student/applications/{missing_app_id}/decision-passport",
        headers=applicant_headers,
    ).get_json()

    assert p_missing["documents"]["overall_status"] == "INCOMPLETE"
    assert "income_certificate" in p_missing["documents"]["missing_documents"]
    assert "id_proof" in p_missing["documents"]["missing_documents"]
    assert p_missing["documents"]["verified_count"] < p_missing["documents"]["required_count"]
    print(f"Missing documents correctly exposed: {p_missing['documents']['missing_documents']}")
    print(">>> TEST 7 PASSED: Missing documents accurately surfaced in passport.")

    # -------------------------------------------------------------
    # TEST 8: Application with mismatched documents
    # -------------------------------------------------------------
    log_test("TEST 8: Application with Mismatched Documents")
    form_mismatch = {
        "academic_score": "95.0", # Form claims 95.0
        "previous_score": "84.0",
        "attendance": "90.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(mismatch_marksheet_pdf), "test_marksheet_mismatch.pdf"), # PDF has 72.0
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }
    res_mis_sub = client.post(
        "/submit-application-full",
        data=form_mismatch,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res_mis_sub.status_code == 201
    mismatch_app_id = res_mis_sub.get_json()["application_id"]

    p_mismatch = client.get(
        f"/student/applications/{mismatch_app_id}/decision-passport",
        headers=applicant_headers,
    ).get_json()

    assert p_mismatch["documents"]["overall_status"] == "NEEDS_REVIEW"
    assert "marksheet" in p_mismatch["documents"]["mismatched_documents"]
    marksheet_item = next(
        item for item in p_mismatch["documents"]["items"] if item["document_type"] == "marksheet"
    )
    assert marksheet_item["verification_status"] == "MISMATCH"
    assert marksheet_item["mismatch_details"] is not None
    print(f"Mismatched document details exposed: {marksheet_item['mismatch_details']}")
    print(">>> TEST 8 PASSED: Mismatched document details accurately surfaced in passport.")

    # -------------------------------------------------------------
    # TEST 9: Application with eligibility failure
    # -------------------------------------------------------------
    log_test("TEST 9: Application with Eligibility Failure")
    form_elig_fail = {
        "academic_score": "42.0",  # Below MERIT minimum (75.0)
        "previous_score": "48.0",  # Below MERIT minimum (70.0)
        "attendance": "55.0",      # Below MERIT minimum (75.0)
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }
    res_ef_sub = client.post(
        "/submit-application-full",
        data=form_elig_fail,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res_ef_sub.status_code == 201
    elig_fail_app_id = res_ef_sub.get_json()["application_id"]

    p_elig_fail = client.get(
        f"/student/applications/{elig_fail_app_id}/decision-passport",
        headers=applicant_headers,
    ).get_json()

    assert p_elig_fail["eligibility"]["eligible"] is False
    assert p_elig_fail["eligibility"]["failed_count"] > 0
    assert len(p_elig_fail["eligibility"]["failed_rules"]) > 0
    assert len(p_elig_fail["eligibility"]["failed_reasons"]) > 0
    failed_codes = [r["rule_code"] for r in p_elig_fail["eligibility"]["failed_rules"]]
    print(f"Failed rule codes: {failed_codes}")
    print(f"Failed rule explanations: {p_elig_fail['eligibility']['failed_reasons']}")
    print(">>> TEST 9 PASSED: Failed eligibility rules and clear explanations exposed.")

    # -------------------------------------------------------------
    # TEST 10: Application with appeal
    # -------------------------------------------------------------
    log_test("TEST 10: Application with Appeal Lifecycle")
    # Reject the eligibility failure application first to allow appeal
    client.post(
        "/admin/decision",
        data=json.dumps({
            "application_id": elig_fail_app_id,
            "decision": "REJECTED",
            "reason": "Does not meet score requirements.",
        }),
        content_type="application/json",
        headers=admin_headers,
    )

    # Submit appeal
    appeal_reason = "Submitting medical certificate for the examination semester."
    app_res = client.post(
        "/student/appeals",
        data=json.dumps({
            "application_id": elig_fail_app_id,
            "reason": appeal_reason,
        }),
        content_type="application/json",
        headers=applicant_headers,
    )
    assert app_res.status_code == 201
    appeal_id = app_res.get_json()["appeal"]["id"]

    # Verify passport shows pending appeal
    p_appeal_pending = client.get(
        f"/student/applications/{elig_fail_app_id}/decision-passport",
        headers=applicant_headers,
    ).get_json()
    assert p_appeal_pending["appeal"]["has_appeal"] is True
    assert p_appeal_pending["appeal"]["status"] == "PENDING"
    assert p_appeal_pending["appeal"]["reason"] == appeal_reason

    # Admin reviews appeal
    review_res = client.post(
        f"/admin/appeals/{appeal_id}/review",
        data=json.dumps({
            "status": "RESOLVED",
            "review_comment": "Re-evaluation approved under medical circumstances.",
        }),
        content_type="application/json",
        headers=admin_headers,
    )
    assert review_res.status_code == 200

    # Verify passport shows resolved appeal
    p_appeal_resolved = client.get(
        f"/student/applications/{elig_fail_app_id}/decision-passport",
        headers=applicant_headers,
    ).get_json()
    assert p_appeal_resolved["appeal"]["has_appeal"] is True
    assert p_appeal_resolved["appeal"]["status"] == "RESOLVED"
    assert p_appeal_resolved["appeal"]["review_comment"] == "Re-evaluation approved under medical circumstances."
    print(f"Appeal exposed in passport: status={p_appeal_resolved['appeal']['status']}, comment={p_appeal_resolved['appeal']['review_comment']}")
    print(">>> TEST 10 PASSED: Appeal status and review comment properly exposed in Decision Passport.")

    log_test("ALL 10 DECISION PASSPORT FOCUSED TESTS PASSED!")


if __name__ == "__main__":
    run_decision_passport_tests()
