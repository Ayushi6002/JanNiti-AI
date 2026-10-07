"""
test_eligibility_simulator.py
-----------------------------
Focused test suite for FEATURE 2: WHAT-IF ELIGIBILITY SIMULATOR.

Tests:
1. Nonexistent application -> 404
2. Unauthorized applicant access -> 403
3. Admin access to simulator -> 200 on both student and admin routes
4. Invalid override validation (unknown field, out of range, negative, non-numeric) -> 400
5. Eligible application simulated with no change (baseline simulation) -> eligible remains True
6. Ineligible application with attendance below threshold (72 vs 75) simulated to 75 -> false -> true
7. Insufficient improvement (attendance 72 -> 73 when 75 required) -> remains false
8. Multiple overrides simulated simultaneously (academic_score + attendance) -> both applied
9. Income upper-bound simulation (NEED_BASED scheme decrease income) -> gap, direction DECREASE, resolves rule
10. Document verification failure -> unverified documents are NEVER bypassed by simulation
11. Persistence protection -> actual application data in DB remains 100% unchanged, no side effects
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
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def run_eligibility_simulator_tests():
    client = app.test_client()

    log_test("STEP 0: Authenticating Test Users")
    applicant_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
    applicant_token = applicant_auth.session.access_token
    applicant_headers = {
        "Authorization": f"Bearer {applicant_token}",
        "Content-Type": "application/json",
    }
    applicant_id = applicant_auth.user.id
    print(f"Applicant authenticated. ID: {applicant_id}")

    admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    admin_token = admin_auth.session.access_token
    admin_headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }
    admin_id = admin_auth.user.id
    print(f"Admin authenticated. ID: {admin_id}")

    # Load test PDFs for creating applications with real document verification state
    with open("test_marksheet.pdf", "rb") as f:
        marksheet_pdf = f.read()
    with open("test_id_proof.pdf", "rb") as f:
        id_proof_pdf = f.read()
    with open("test_income_certificate.pdf", "rb") as f:
        income_pdf = f.read()

    # -------------------------------------------------------------
    # TEST 1: Nonexistent Application -> 404
    # -------------------------------------------------------------
    log_test("TEST 1: Nonexistent Application -> 404")
    res_404 = client.post(
        "/student/applications/00000000-0000-0000-0000-000000000000/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"attendance": 80}},
    )
    print(f"Response status: {res_404.status_code}")
    assert res_404.status_code == 404, f"Expected 404, got {res_404.status_code}"
    assert "error" in res_404.get_json()
    print(">>> TEST 1 PASSED: Nonexistent application correctly returned 404.")

    # -------------------------------------------------------------
    # TEST 2: Applicant Cannot Simulate Another Applicant's Application -> 403
    # -------------------------------------------------------------
    log_test("TEST 2: Applicant Forbidden Access to Another Applicant's Application -> 403")
    other_app_res = (
        supabase
        .table("applications")
        .insert({
            "applicant_id": admin_id,
            "scholarship_scheme_id": "91fc26f7-e746-4dae-862b-ddc1a8c3527c",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 70.0,
            "annual_income": 200000.0,
            "application_category": "GENERAL",
            "status": "SUBMITTED",
        })
        .execute()
    )
    other_app_id = other_app_res.data[0]["id"]
    print(f"Created application {other_app_id} belonging to user {admin_id}")

    res_403 = client.post(
        f"/student/applications/{other_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"attendance": 80}},
    )
    print(f"Response status: {res_403.status_code}")
    assert res_403.status_code == 403, f"Expected 403, got {res_403.status_code}"
    assert "error" in res_403.get_json()
    print(">>> TEST 2 PASSED: Applicant blocked with 403 when requesting another's application.")

    # -------------------------------------------------------------
    # TEST 3: Admin Can Simulate Any Application -> 200
    # -------------------------------------------------------------
    log_test("TEST 3: Admin Access to Simulation -> 200")
    res_admin_student_route = client.post(
        f"/student/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"attendance": 85}},
    )
    assert res_admin_student_route.status_code == 200, (
        f"Admin accessing student simulate route failed: {res_admin_student_route.status_code}"
    )

    res_admin_admin_route = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"attendance": 85}},
    )
    assert res_admin_admin_route.status_code == 200, (
        f"Admin accessing admin simulate route failed: {res_admin_admin_route.status_code}"
    )
    print(">>> TEST 3 PASSED: Admin successfully accessed simulation on both routes.")

    # -------------------------------------------------------------
    # TEST 4: Invalid Simulation Inputs -> 400
    # -------------------------------------------------------------
    log_test("TEST 4: Invalid Simulation Overrides Validation -> 400")
    # Subtest 4a: Disallowed field
    res_inv_field = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"fake_field": 100}},
    )
    assert res_inv_field.status_code == 400, f"Expected 400 for invalid field, got {res_inv_field.status_code}"
    assert "Invalid override field" in res_inv_field.get_json()["error"]

    # Subtest 4b: Negative attendance
    res_neg_att = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"attendance": -5}},
    )
    assert res_neg_att.status_code == 400, f"Expected 400 for negative attendance, got {res_neg_att.status_code}"

    # Subtest 4c: Attendance > 100
    res_high_att = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"attendance": 105}},
    )
    assert res_high_att.status_code == 400, f"Expected 400 for attendance > 100, got {res_high_att.status_code}"

    # Subtest 4d: Negative income
    res_neg_inc = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"annual_income": -500}},
    )
    assert res_neg_inc.status_code == 400, f"Expected 400 for negative income, got {res_neg_inc.status_code}"

    # Subtest 4e: Non-numeric score
    res_str_score = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": {"academic_score": "excellent"}},
    )
    assert res_str_score.status_code == 400, f"Expected 400 for non-numeric score, got {res_str_score.status_code}"

    # Subtest 4f: Malformed overrides type
    res_bad_type = client.post(
        f"/admin/applications/{other_app_id}/eligibility/simulate",
        headers=admin_headers,
        json={"overrides": "not_a_dictionary"},
    )
    assert res_bad_type.status_code == 400, f"Expected 400 for bad type, got {res_bad_type.status_code}"
    print(">>> TEST 4 PASSED: All invalid inputs properly rejected with 400 Bad Request.")

    # -------------------------------------------------------------
    # Create a fully verified, eligible application for the applicant
    # -------------------------------------------------------------
    log_test("CREATING FULLY VERIFIED ELIGIBLE APPLICATION (MERIT)")
    form_eligible = {
        "academic_score": "88.5",
        "previous_score": "84.0",
        "attendance": "90.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }
    submit_res = client.post(
        "/submit-application-full",
        data=form_eligible,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert submit_res.status_code == 201, f"Eligible submission failed: {submit_res.get_json()}"
    eligible_app_id = submit_res.get_json()["application_id"]
    print(f"Eligible application created: {eligible_app_id}")

    # -------------------------------------------------------------
    # TEST 5: Eligible Application Simulated With No Change
    # -------------------------------------------------------------
    log_test("TEST 5: Eligible Application Simulated With No Change -> Remains Eligible")
    res_sim_nochange = client.post(
        f"/student/applications/{eligible_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {}},
    )
    assert res_sim_nochange.status_code == 200, f"Simulation failed: {res_sim_nochange.get_json()}"
    sim_data_5 = res_sim_nochange.get_json()

    assert sim_data_5["simulation"]["eligible"] is True
    assert sim_data_5["simulation"]["changed"] is False
    assert sim_data_5["simulation"]["became_eligible"] is False
    assert sim_data_5["current_result"]["eligible"] is True
    assert sim_data_5["simulated_result"]["eligible"] is True
    assert len(sim_data_5["simulated_result"]["failed_rules"]) == 0
    assert len(sim_data_5["changes"]) == 0
    assert len(sim_data_5["improvements"]) == 0
    assert "satisfies all eligibility requirements" in sim_data_5["message"]
    print(">>> TEST 5 PASSED: Baseline simulation on eligible application remains eligible.")

    # -------------------------------------------------------------
    # Create an ineligible application: Attendance 72% (< 75% required by MERIT)
    # -------------------------------------------------------------
    log_test("CREATING INELIGIBLE APPLICATION (ATTENDANCE 72% < 75%)")
    form_low_att = {
        "academic_score": "88.5",
        "previous_score": "84.0",
        "attendance": "72.0",
        "annual_income": "250000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
    }
    submit_res_att = client.post(
        "/submit-application-full",
        data=form_low_att,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert submit_res_att.status_code == 201, f"Low attendance submission failed: {submit_res_att.get_json()}"
    low_att_app_id = submit_res_att.get_json()["application_id"]
    print(f"Low attendance application created: {low_att_app_id}")

    # -------------------------------------------------------------
    # TEST 6: Simulate Attendance at Required Threshold (72 -> 75)
    # -------------------------------------------------------------
    log_test("TEST 6: Simulate Attendance at Required Threshold -> False to True")
    res_sim_att_pass = client.post(
        f"/student/applications/{low_att_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"attendance": 75.0}},
    )
    assert res_sim_att_pass.status_code == 200, f"Simulation failed: {res_sim_att_pass.get_json()}"
    sim_data_6 = res_sim_att_pass.get_json()

    assert sim_data_6["current_result"]["eligible"] is False
    assert "MIN_ATTENDANCE" in sim_data_6["current_result"]["failed_rules"]
    assert sim_data_6["simulated_result"]["eligible"] is True
    assert len(sim_data_6["simulated_result"]["failed_rules"]) == 0
    assert sim_data_6["simulation"]["eligible"] is True
    assert sim_data_6["simulation"]["changed"] is True
    assert sim_data_6["simulation"]["became_eligible"] is True
    assert sim_data_6["changes"]["attendance"]["current"] == 72.0
    assert sim_data_6["changes"]["attendance"]["simulated"] == 75.0

    # Verify improvements list contains MIN_ATTENDANCE marked RESOLVED
    resolved_rules = [i["rule"] for i in sim_data_6["improvements"]]
    assert "MIN_ATTENDANCE" in resolved_rules
    att_improvement = [i for i in sim_data_6["improvements"] if i["rule"] == "MIN_ATTENDANCE"][0]
    assert att_improvement["status"] == "RESOLVED"
    assert att_improvement["required_value"] == 75

    # Verify recommended changes from baseline
    recommended = sim_data_6["recommended_changes"]
    att_rec = [r for r in recommended if r["field"] == "attendance"]
    assert len(att_rec) == 1
    assert att_rec[0]["target"] == 75.0
    assert att_rec[0]["gap"] == 3.0
    assert att_rec[0]["direction"] == "INCREASE"
    print(">>> TEST 6 PASSED: Simulating attendance to threshold successfully makes application eligible.")

    # -------------------------------------------------------------
    # TEST 7: Simulate Improvement That Is NOT Sufficient (72 -> 73)
    # -------------------------------------------------------------
    log_test("TEST 7: Simulate Insufficient Improvement (72 -> 73) -> Still Ineligible")
    res_sim_att_fail = client.post(
        f"/student/applications/{low_att_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"attendance": 73.0}},
    )
    assert res_sim_att_fail.status_code == 200, f"Simulation failed: {res_sim_att_fail.get_json()}"
    sim_data_7 = res_sim_att_fail.get_json()

    assert sim_data_7["current_result"]["eligible"] is False
    assert sim_data_7["simulated_result"]["eligible"] is False
    assert sim_data_7["simulation"]["eligible"] is False
    assert sim_data_7["simulation"]["became_eligible"] is False
    assert "MIN_ATTENDANCE" in sim_data_7["simulated_result"]["failed_rules"]
    assert len(sim_data_7["improvements"]) == 0
    rem_failed = [r["rule"] for r in sim_data_7["remaining_failures"]]
    assert "MIN_ATTENDANCE" in rem_failed
    print(">>> TEST 7 PASSED: Insufficient improvement correctly keeps application ineligible.")

    # -------------------------------------------------------------
    # TEST 8: Multiple Overrides (Academic Score + Attendance)
    # -------------------------------------------------------------
    log_test("TEST 8: Multiple Overrides Simulated Together")
    # Update low_att_app in DB so that academic_score is also 72.0 (below required 75.0)
    supabase.table("applications").update({"academic_score": 72.0}).eq("id", low_att_app_id).execute()

    res_sim_multi = client.post(
        f"/student/applications/{low_att_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"academic_score": 85.0, "attendance": 80.0}},
    )
    assert res_sim_multi.status_code == 200, f"Simulation failed: {res_sim_multi.get_json()}"
    sim_data_8 = res_sim_multi.get_json()

    assert "academic_score" in sim_data_8["changes"]
    assert "attendance" in sim_data_8["changes"]
    assert sim_data_8["changes"]["academic_score"]["current"] == 72.0
    assert sim_data_8["changes"]["academic_score"]["simulated"] == 85.0
    assert sim_data_8["changes"]["attendance"]["current"] == 72.0
    assert sim_data_8["changes"]["attendance"]["simulated"] == 80.0
    assert sim_data_8["simulated_result"]["eligible"] is True
    multi_improved = {i["rule"] for i in sim_data_8["improvements"]}
    assert "MIN_ACADEMIC_SCORE" in multi_improved
    assert "MIN_ATTENDANCE" in multi_improved
    print(">>> TEST 8 PASSED: Multiple overrides simultaneously reflected and evaluated.")

    # Revert academic score back to 88.5
    supabase.table("applications").update({"academic_score": 88.5}).eq("id", low_att_app_id).execute()

    # -------------------------------------------------------------
    # TEST 9: Income Upper-Bound Simulation (MAX_ANNUAL_INCOME)
    # -------------------------------------------------------------
    log_test("TEST 9: Income Upper-Bound Simulation (MAX_ANNUAL_INCOME)")
    # Update eligible_app_id in DB to have annual_income = 900,000 (> 800,000 limit)
    supabase.table("applications").update({"annual_income": 900000.0}).eq("id", eligible_app_id).execute()

    # Baseline check: MAX_ANNUAL_INCOME fails
    res_inc_baseline = client.post(
        f"/student/applications/{eligible_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {}},
    )
    sim_inc_base = res_inc_baseline.get_json()
    assert sim_inc_base["current_result"]["eligible"] is False
    assert "MAX_ANNUAL_INCOME" in sim_inc_base["current_result"]["failed_rules"]

    # Verify requirements analysis and recommended changes show DECREASE direction
    inc_rec = [r for r in sim_inc_base["recommended_changes"] if r["field"] == "annual_income"]
    assert len(inc_rec) == 1
    assert inc_rec[0]["direction"] == "DECREASE"
    assert inc_rec[0]["current"] == 900000.0
    assert inc_rec[0]["target"] == 800000.0
    assert inc_rec[0]["gap"] == 100000.0

    # Simulate decreasing income below maximum allowed threshold: 750,000 <= 800,000
    res_sim_inc = client.post(
        f"/student/applications/{eligible_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"annual_income": 750000.0}},
    )
    assert res_sim_inc.status_code == 200
    sim_data_9 = res_sim_inc.get_json()
    assert sim_data_9["simulated_result"]["eligible"] is True
    assert sim_data_9["simulation"]["became_eligible"] is True
    inc_improvements = [i["rule"] for i in sim_data_9["improvements"]]
    assert "MAX_ANNUAL_INCOME" in inc_improvements

    # Revert eligible application income back to 250,000
    supabase.table("applications").update({"annual_income": 250000.0}).eq("id", eligible_app_id).execute()
    print(">>> TEST 9 PASSED: Income upper-bound decrease simulation successfully resolves eligibility.")

    # -------------------------------------------------------------
    # TEST 10: Document Verification Failure Respected by Simulation
    # -------------------------------------------------------------
    log_test("TEST 10: Document Verification Failure Respected by Simulation")
    # Submit application with missing income certificate
    form_missing_doc = {
        "academic_score": "95.0",
        "previous_score": "90.0",
        "attendance": "95.0",
        "annual_income": "200000.0",
        "application_category": "GENERAL",
        "scholarship_scheme": "MERIT",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        # income_certificate missing!
    }
    submit_res_missing = client.post(
        "/submit-application-full",
        data=form_missing_doc,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert submit_res_missing.status_code == 201
    missing_app_id = submit_res_missing.get_json()["application_id"]
    print(f"Missing doc application created: {missing_app_id}")

    # Simulate even higher scores
    res_sim_doc = client.post(
        f"/student/applications/{missing_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"academic_score": 99.0, "attendance": 99.0}},
    )
    assert res_sim_doc.status_code == 200
    sim_data_10 = res_sim_doc.get_json()

    assert sim_data_10["simulated_result"]["eligible"] is False
    assert "DOCUMENTS_VERIFIED" in sim_data_10["simulated_result"]["failed_rules"]
    assert any(f["rule"] == "DOCUMENTS_VERIFIED" for f in sim_data_10["remaining_failures"])
    assert "Document verification requirements" in sim_data_10["message"]
    print(">>> TEST 10 PASSED: Unverified documents correctly prevent simulated eligibility.")

    # -------------------------------------------------------------
    # TEST 11: Persistence Protection (Read-Only Guarantee)
    # -------------------------------------------------------------
    log_test("TEST 11: Persistence Protection -> Zero Database Side Effects")
    # Capture application state before simulation
    before_row = (
        supabase
        .table("applications")
        .select("academic_score, previous_score, attendance, annual_income, application_category, status")
        .eq("id", low_att_app_id)
        .single()
        .execute()
        .data
    )

    # Capture record counts of other tables
    pred_count_before = len(supabase.table("ai_predictions").select("id").eq("application_id", low_att_app_id).execute().data or [])
    dec_count_before = len(supabase.table("decisions").select("id").eq("application_id", low_att_app_id).execute().data or [])
    audit_count_before = len(supabase.table("audit_logs").select("id").eq("application_id", low_att_app_id).execute().data or [])
    appeal_count_before = len(supabase.table("appeals").select("id").eq("application_id", low_att_app_id).execute().data or [])

    # Run aggressive simulation with multiple overrides
    client.post(
        f"/student/applications/{low_att_app_id}/eligibility/simulate",
        headers=applicant_headers,
        json={"overrides": {"academic_score": 99.0, "attendance": 99.0, "annual_income": 50000.0}},
    )

    # Fetch application state after simulation
    after_row = (
        supabase
        .table("applications")
        .select("academic_score, previous_score, attendance, annual_income, application_category, status")
        .eq("id", low_att_app_id)
        .single()
        .execute()
        .data
    )

    pred_count_after = len(supabase.table("ai_predictions").select("id").eq("application_id", low_att_app_id).execute().data or [])
    dec_count_after = len(supabase.table("decisions").select("id").eq("application_id", low_att_app_id).execute().data or [])
    audit_count_after = len(supabase.table("audit_logs").select("id").eq("application_id", low_att_app_id).execute().data or [])
    appeal_count_after = len(supabase.table("appeals").select("id").eq("application_id", low_att_app_id).execute().data or [])

    # Assert 100% equality
    assert before_row == after_row, f"Application row was mutated! Before: {before_row}, After: {after_row}"
    assert float(after_row["attendance"]) == 72.0, "Attendance was persistently changed!"
    assert pred_count_before == pred_count_after, "AI predictions were erroneously created!"
    assert dec_count_before == dec_count_after, "Decisions were erroneously created!"
    assert audit_count_before == audit_count_after, "Audit logs were erroneously created!"
    assert appeal_count_before == appeal_count_after, "Appeals were erroneously created!"

    print(">>> TEST 11 PASSED: Strict read-only guarantee confirmed. Zero database side effects.")

    log_test("ALL 11 ELIGIBILITY SIMULATOR FOCUSED TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_eligibility_simulator_tests()
