"""
test_category_certificate.py
-----------------------------
Comprehensive focused test suite for FEATURE 4: CATEGORY CERTIFICATE VERIFICATION.

Tests all required scenarios:
1. Valid matching OBC certificate -> MATCH
2. Valid matching SC certificate -> MATCH
3. Category mismatch -> MISMATCH
4. Name mismatch -> detected
5. Missing category field -> UNCERTAIN / INCOMPLETE
6. Missing Category Certificate when required -> missing / incomplete
7. Category Certificate not required -> application continues normally
8. Certificate with valid date -> accepted
9. Expired certificate -> temporal issue detected
10. Future issue date -> temporal issue detected
11. Category normalization works across all standard variations
12. Student authorization remains correct
13. Admin access remains correct
14. Existing Feature 3 anomaly detection still works with category certificate
15. Existing Feature 1 Decision Passport still works
16. Existing Feature 2 Eligibility Simulator still works
17. Full pipeline integration with CATEGORY scheme
"""

import io
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase
from backend.document_extractor import (
    extract_category_certificate_fields,
    normalize_category,
)
from backend.document_cross_checker import (
    compare_category_certificate_with_application,
)
from backend.verification_service import generate_verification_summary
from backend.pipeline_service import submit_and_process_application
from backend.passport_service import build_decision_passport
from backend.eligibility_simulator_service import simulate_eligibility
from backend.anomaly_detection_service import (
    detect_field_inconsistencies,
    detect_temporal_anomalies,
    get_application_anomalies,
)


def log_test(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def make_pdf(lines: list[str]) -> bytes:
    """Generate minimal valid PDF bytes containing text lines for test documents."""
    stream = "BT /F1 12 Tf 50 750 Td 14 TL\n"
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream += f"({escaped}) '\n"
    stream += "ET\n"
    stream_bytes = stream.encode("latin1")

    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    objs.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objs.append(
        b"5 0 obj\n<< /Length "
        + str(len(stream_bytes)).encode("ascii")
        + b" >>\nstream\n"
        + stream_bytes
        + b"endstream\nendobj\n"
    )

    out = b"%PDF-1.4\n"
    xref = [len(out)]
    for obj in objs:
        out += obj
        xref.append(len(out))
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for pos in xref[:-1]:
        out += f"{pos:010d} 00000 n \n".encode("ascii")
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode("ascii") + b"\n%%EOF\n"
    return out


def run_all_feature_4_tests():
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

    # Load baseline test PDFs
    with open("test_marksheet.pdf", "rb") as f:
        marksheet_pdf = f.read()
    with open("test_id_proof.pdf", "rb") as f:
        id_proof_pdf = f.read()
    with open("test_income_certificate.pdf", "rb") as f:
        income_pdf = f.read()

    # -------------------------------------------------------------
    # TEST 1: Valid Matching OBC Certificate -> MATCH
    # -------------------------------------------------------------
    log_test("TEST 1: Valid Matching OBC Certificate -> MATCH")
    obc_text = (
        "Category Certificate\n"
        "Student Name: Jan Niti Test User\n"
        "Category: Other Backward Class\n"
        "Certificate Number: OBC/2024/7890\n"
        "Issuing Authority: Sub-Divisional Magistrate\n"
        "Issue Date: 2024-02-15\n"
        "Expiry Date: 2028-02-15"
    )
    obc_extracted = extract_category_certificate_fields(obc_text)
    assert obc_extracted["student_name"] == "Jan Niti Test User"
    assert obc_extracted["category"] == "Other Backward Class"
    assert obc_extracted["normalized_category"] == "OBC"
    assert obc_extracted["certificate_number"] == "OBC/2024/7890"
    assert obc_extracted["issuing_authority"] == "Sub-Divisional Magistrate"
    assert obc_extracted["issue_date"] == "2024-02-15"
    assert obc_extracted["expiry_date"] == "2028-02-15"

    app_data_obc = {"application_category": "OBC"}
    profile_data = {"full_name": "Jan Niti Test User"}
    obc_comp = compare_category_certificate_with_application(
        obc_extracted, app_data_obc, profile_data
    )
    assert obc_comp["overall_status"] == "MATCH"
    assert obc_comp["verification_status"] == "VERIFIED"
    assert obc_comp["verification_score"] == 100.0
    assert obc_comp["category_check"]["status"] == "MATCH"
    assert obc_comp["name_check"]["status"] == "MATCH"
    assert obc_comp["validity_check"]["status"] == "VALID"
    print(">>> TEST 1 PASSED: Valid matching OBC certificate correctly verified with 100% score.")

    # -------------------------------------------------------------
    # TEST 2: Valid Matching SC Certificate -> MATCH
    # -------------------------------------------------------------
    log_test("TEST 2: Valid Matching SC Certificate -> MATCH")
    sc_text = (
        "GOVERNMENT CASTE CERTIFICATE\n"
        "Student Name: Jan Niti Test User\n"
        "Social Category: Scheduled Caste\n"
        "Certificate No: SC-998877\n"
        "Issued By: District Magistrate\n"
        "Issue Date: 2023-08-10"
    )
    sc_extracted = extract_category_certificate_fields(sc_text)
    assert sc_extracted["normalized_category"] == "SC"
    assert sc_extracted["certificate_number"] == "SC-998877"

    app_data_sc = {"application_category": "SC"}
    sc_comp = compare_category_certificate_with_application(
        sc_extracted, app_data_sc, profile_data
    )
    assert sc_comp["overall_status"] == "MATCH"
    assert sc_comp["verification_status"] == "VERIFIED"
    assert sc_comp["category_check"]["status"] == "MATCH"
    print(">>> TEST 2 PASSED: Valid matching SC certificate correctly verified with MATCH.")

    # -------------------------------------------------------------
    # TEST 3: Category Mismatch -> MISMATCH
    # -------------------------------------------------------------
    log_test("TEST 3: Category Mismatch -> MISMATCH")
    mismatch_comp = compare_category_certificate_with_application(
        sc_extracted, {"application_category": "OBC"}, profile_data
    )
    assert mismatch_comp["overall_status"] == "MISMATCH"
    assert mismatch_comp["verification_status"] == "MISMATCH"
    assert mismatch_comp["category_check"]["status"] == "MISMATCH"
    assert "does not match" in mismatch_comp["category_check"]["reason"]
    print(">>> TEST 3 PASSED: Category mismatch declared OBC vs certificate SC correctly flagged MISMATCH.")

    # -------------------------------------------------------------
    # TEST 4: Name Mismatch -> Detected
    # -------------------------------------------------------------
    log_test("TEST 4: Name Mismatch -> Detected")
    wrong_name_extracted = dict(obc_extracted)
    wrong_name_extracted["student_name"] = "Rahul Kumar Sharma"
    name_mismatch_comp = compare_category_certificate_with_application(
        wrong_name_extracted, app_data_obc, profile_data
    )
    assert name_mismatch_comp["name_check"]["status"] == "MISMATCH"
    assert name_mismatch_comp["overall_status"] == "MISMATCH"
    assert "Rahul Kumar Sharma" in name_mismatch_comp["name_check"]["reason"]
    print(">>> TEST 4 PASSED: Student name mismatch between certificate and profile detected.")

    # -------------------------------------------------------------
    # TEST 5: Missing Category Field -> UNCERTAIN / INCOMPLETE
    # -------------------------------------------------------------
    log_test("TEST 5: Missing Category Field -> UNCERTAIN / INCOMPLETE")
    missing_cat_extracted = dict(obc_extracted)
    missing_cat_extracted["category"] = None
    missing_cat_extracted["normalized_category"] = None
    missing_cat_comp = compare_category_certificate_with_application(
        missing_cat_extracted, app_data_obc, profile_data
    )
    assert missing_cat_comp["category_check"]["status"] == "MISSING"
    assert missing_cat_comp["overall_status"] == "INCOMPLETE"
    assert missing_cat_comp["verification_status"] == "NEEDS_REVIEW"
    print(">>> TEST 5 PASSED: Missing category on certificate flagged INCOMPLETE.")

    # -------------------------------------------------------------
    # TEST 6: Missing Category Certificate When Required -> INCOMPLETE
    # -------------------------------------------------------------
    log_test("TEST 6: Missing Category Certificate When Required by CATEGORY Scheme")
    # Scheme CATEGORY requires ['marksheet', 'id_proof', 'category_certificate', 'income_certificate']
    t6_form = {
        "academic_score": "80.0",
        "previous_score": "78.0",
        "attendance": "85.0",
        "annual_income": "200000.0",
        "application_category": "OBC",
        "scholarship_scheme": "CATEGORY",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
        # category_certificate deliberately omitted
    }
    res6 = client.post(
        "/submit-application-full",
        data=t6_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res6.status_code == 201, f"Failed: {res6.get_json()}"
    data6 = res6.get_json()
    assert data6["status"] == "HUMAN_REVIEW", "Must route to HUMAN_REVIEW, never auto-reject!"
    assert data6["verification_summary"]["overall_status"] == "INCOMPLETE"
    assert "category_certificate" in data6["verification_summary"]["missing_documents"]
    print(">>> TEST 6 PASSED: Missing category certificate when required flagged INCOMPLETE and routed to HUMAN_REVIEW.")

    # -------------------------------------------------------------
    # TEST 7: Category Certificate Not Required -> Application Continues
    # -------------------------------------------------------------
    log_test("TEST 7: Category Certificate Not Required (MERIT Scheme)")
    # Scheme MERIT does not require category_certificate
    t7_form = {
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
    res7 = client.post(
        "/submit-application-full",
        data=t7_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res7.status_code == 201, f"Failed: {res7.get_json()}"
    data7 = res7.get_json()
    assert data7["status"] == "HUMAN_REVIEW"
    assert data7["verification_summary"]["overall_status"] == "VERIFIED"
    assert "category_certificate" not in data7["verification_summary"]["required_documents"]
    assert "category_certificate" not in data7["verification_summary"]["missing_documents"]
    print(">>> TEST 7 PASSED: Scheme without category_certificate requirement proceeds cleanly.")

    # -------------------------------------------------------------
    # TEST 8: Certificate with Valid Date -> Accepted
    # -------------------------------------------------------------
    log_test("TEST 8: Certificate with Valid Date -> Accepted")
    valid_date_extracted = dict(obc_extracted)
    valid_date_extracted["issue_date"] = "2024-01-01"
    valid_date_extracted["expiry_date"] = (datetime.now(timezone.utc).date() + timedelta(days=365)).isoformat()
    val_comp = compare_category_certificate_with_application(
        valid_date_extracted, app_data_obc, profile_data
    )
    assert val_comp["validity_check"]["status"] == "VALID"
    assert val_comp["overall_status"] == "MATCH"
    print(">>> TEST 8 PASSED: Valid current dates correctly accepted.")

    # -------------------------------------------------------------
    # TEST 9: Expired Certificate -> Temporal Issue Detected
    # -------------------------------------------------------------
    log_test("TEST 9: Expired Certificate -> Temporal Issue Detected")
    expired_extracted = dict(obc_extracted)
    expired_extracted["issue_date"] = "2020-01-01"
    expired_extracted["expiry_date"] = "2022-01-01"  # clearly expired
    exp_comp = compare_category_certificate_with_application(
        expired_extracted, app_data_obc, profile_data
    )
    assert exp_comp["validity_check"]["status"] == "EXPIRED"
    assert exp_comp["overall_status"] == "MISMATCH"
    print(">>> TEST 9 PASSED: Expired certificate correctly detected as EXPIRED.")

    # -------------------------------------------------------------
    # TEST 10: Future Issue Date -> Temporal Issue Detected
    # -------------------------------------------------------------
    log_test("TEST 10: Future Issue Date -> Temporal Issue Detected")
    future_extracted = dict(obc_extracted)
    future_extracted["issue_date"] = (datetime.now(timezone.utc).date() + timedelta(days=60)).isoformat()
    future_extracted["expiry_date"] = None
    fut_comp = compare_category_certificate_with_application(
        future_extracted, app_data_obc, profile_data
    )
    assert fut_comp["validity_check"]["status"] == "FUTURE_DATE"
    assert fut_comp["overall_status"] == "MISMATCH"
    print(">>> TEST 10 PASSED: Impossible future issue date detected.")

    # -------------------------------------------------------------
    # TEST 11: Category Normalization Works
    # -------------------------------------------------------------
    log_test("TEST 11: Category Normalization Rules")
    assert normalize_category("OBC") == "OBC"
    assert normalize_category("Other Backward Class") == "OBC"
    assert normalize_category("other backward classes") == "OBC"
    assert normalize_category("SC") == "SC"
    assert normalize_category("Scheduled Caste") == "SC"
    assert normalize_category("scheduled castes") == "SC"
    assert normalize_category("ST") == "ST"
    assert normalize_category("Scheduled Tribe") == "ST"
    assert normalize_category("scheduled tribes") == "ST"
    assert normalize_category("EWS") == "EWS"
    assert normalize_category("Economically Weaker Section") == "EWS"
    assert normalize_category("GEN") == "GENERAL"
    assert normalize_category("GENERAL") == "GENERAL"
    assert normalize_category("General Category") == "GENERAL"
    assert normalize_category("Unreserved") == "GENERAL"
    print(">>> TEST 11 PASSED: All category variations normalize to canonical representations.")

    # -------------------------------------------------------------
    # TEST 12: Student Authorization Remains Correct
    # -------------------------------------------------------------
    log_test("TEST 12: Student Authorization on Verification Summary")
    app_id = data6["application_id"]
    ver_res = client.get(
        f"/student/applications/{app_id}/verification",
        headers=applicant_headers,
    )
    assert ver_res.status_code == 200, f"Failed: {ver_res.get_json()}"
    ver_data = ver_res.get_json()
    assert "required_documents" in ver_data
    assert "category_certificate" in ver_data["required_documents"]
    print(">>> TEST 12 PASSED: Student can access own application verification summary.")

    # -------------------------------------------------------------
    # TEST 13: Admin Access Remains Correct
    # -------------------------------------------------------------
    log_test("TEST 13: Admin Access to Detailed Application with Verification Summary")
    admin_res = client.get(
        f"/admin/applications/{app_id}",
        headers=admin_headers,
    )
    assert admin_res.status_code == 200, f"Failed: {admin_res.get_json()}"
    admin_data = admin_res.get_json()
    assert "verification_summary" in admin_data
    assert admin_data["verification_summary"]["overall_status"] == "INCOMPLETE"
    print(">>> TEST 13 PASSED: Admin has full access to application verification details.")

    # -------------------------------------------------------------
    # TEST 14: Existing Feature 3 Anomaly Detection Works With Category Certificate
    # -------------------------------------------------------------
    log_test("TEST 14: Feature 3 Anomaly Detection with Category Certificate")
    doc_incon = detect_field_inconsistencies(
        {"application_category": "OBC"},
        [{
            "document_type": "category_certificate",
            "extracted_data": {"category": "SC", "student_name": "Jan Niti Test User"},
            "file_name": "category_certificate.pdf",
        }],
        {"full_name": "Jan Niti Test User"},
    )
    assert any(a["type"] == "FIELD_MISMATCH" and a["field"] == "application_category" for a in doc_incon)
    print(">>> TEST 14 PASSED: Feature 3 correctly detects category certificate anomalies.")

    # -------------------------------------------------------------
    # TEST 15: Existing Feature 1 Decision Passport Still Works
    # -------------------------------------------------------------
    log_test("TEST 15: Existing Feature 1 Decision Passport Verification")
    passport = build_decision_passport(app_id, {"id": applicant_id, "role": "applicant"})
    assert passport["application"]["id"] == app_id
    assert "documents" in passport
    assert "eligibility" in passport
    print(">>> TEST 15 PASSED: Decision Passport built successfully.")

    # -------------------------------------------------------------
    # TEST 16: Existing Feature 2 Eligibility Simulator Still Works
    # -------------------------------------------------------------
    log_test("TEST 16: Existing Feature 2 Eligibility Simulator Verification")
    sim = simulate_eligibility(
        app_id,
        {"id": applicant_id, "role": "applicant"},
        {"academic_score": 95.0, "application_category": "SC"},
    )
    assert sim.get("application_id") == app_id
    assert "simulation" in sim
    assert "simulated_result" in sim
    print(">>> TEST 16 PASSED: Eligibility Simulator operates normally.")

    # -------------------------------------------------------------
    # TEST 17: Full Pipeline Integration with CATEGORY Scheme + Valid Certificate
    # -------------------------------------------------------------
    log_test("TEST 17: Full Pipeline Submission with CATEGORY Scheme & Valid Category Certificate")
    valid_cat_pdf = make_pdf([
        "GOVERNMENT OF INDIA",
        "CATEGORY CERTIFICATE",
        "Student Name: Jan Niti Test User",
        "Category: Other Backward Class",
        "Certificate Number: CAT-OBC-9988",
        "Issuing Authority: Tehsildar",
        "Issue Date: 2024-03-01",
        "Expiry Date: 2028-03-01",
    ])
    t17_form = {
        "academic_score": "88.5",
        "previous_score": "84.0",
        "attendance": "92.0",
        "annual_income": "250000.0",
        "application_category": "OBC",
        "scholarship_scheme": "CATEGORY",
        "marksheet": (io.BytesIO(marksheet_pdf), "test_marksheet.pdf"),
        "id_proof": (io.BytesIO(id_proof_pdf), "test_id_proof.pdf"),
        "income_certificate": (io.BytesIO(income_pdf), "test_income_certificate.pdf"),
        "category_certificate": (io.BytesIO(valid_cat_pdf), "test_category_certificate.pdf"),
    }
    res17 = client.post(
        "/submit-application-full",
        data=t17_form,
        content_type="multipart/form-data",
        headers=applicant_headers,
    )
    assert res17.status_code == 201, f"Failed: {res17.get_json()}"
    data17 = res17.get_json()
    assert data17["status"] == "HUMAN_REVIEW", "Must route to HUMAN_REVIEW, never auto-approve!"
    assert data17["verification_summary"]["overall_status"] == "VERIFIED"
    assert "category_certificate" in data17["verification_summary"]["documents"]
    cat_doc_info = data17["verification_summary"]["documents"]["category_certificate"]
    assert cat_doc_info["status"] == "VERIFIED"
    assert cat_doc_info["score"] == 100.0
    print(">>> TEST 17 PASSED: Full pipeline with Category Certificate verified with 100% score.")

    print("\n" + "=" * 65)
    print("  ALL 17 FEATURE 4 TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_all_feature_4_tests()
